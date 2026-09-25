#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ABLAEUFE PER KNOPF ANSTOSSEN (Gerhard, 20.09.2026, S8; Mathias, 21.09.2026)
===========================================================================
Gerhard: "Zusaetzlich brauche ich einen Button direkt in der Streamlit-
Oberflaeche, mit dem ich den Scanner nach einem Absturz oder nach GitHub-
Problemen selbst wieder anstossen kann, ohne dich extra fragen zu muessen."

Die Knoepfe stossen nur Ablaeufe an, die SELBST pruefen, ob etwas zu tun ist:
  * Waechter: der Waechter-Hueter (waechterhueter.yml mit
    waechter_noetig.py) startet eine Wache nur waehrend des Handels und nur,
    wenn keine laeuft oder wartet. Er laeuft ohnehin alle sechs Minuten; der
    Knopf holt das sofort nach. Am 18.09.2026 hat GitHub die Wache um 18:26
    Wiener Zeit abgeschaltet, der Hueter hat zwei Minuten spaeter eine neue
    angestossen.
  * Nachtscan: scanner.yml scannt nur, wenn der faellige Scan fehlt
    (scan_noetig.py); angestossen wird ohne "erzwingen".
  * Scanner-Tabelle: scanner_daten.yml baut nur, wenn die Tabelle nicht
    schon mit dem neuesten RS-Universum rechnet; ohne "erzwingen".
Ein Knopf kann deshalb nichts doppelt starten und nichts ausserhalb der
Zeit. Der Token ABLAUF_TOKEN darf nur Ablaeufe im Repo heliot lesen und
starten; die App gibt ihn nur dem vollen Zugang.

Dieses Modul rechnet nur Saetze aus den Antworten der GitHub-API
(GET /repos/{owner}/{repo}/actions/workflows/{datei}/runs) und ist ohne Netz
pruefbar; die Abrufe macht streamlit_app.py.

Aufruf:
    python ablaeufe.py --selbsttest
"""

import argparse
import sys
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

ABLAEUFE = (
    {"schluessel": "waechter", "titel": "Breakout-Wächter",
     "anstoss": "waechterhueter.yml", "zustand": "watcher.yml", "echt_ab_s": 0,
     "knopf": "Wächter prüfen und bei Bedarf starten",
     "erklaerung": ("Der Wächter wacht während des Handels in New York, 9:30 bis 16:00 Uhr New Yorker Zeit, "
                    "also 15:30 bis 22:00 Uhr Wiener Zeit. Über ihn wacht der Hüter, ein zweiter Ablauf, der alle "
                    "sechs Minuten nachsieht, ob der Wächter läuft, und ihn neu startet, wenn er fehlt; der Knopf "
                    "stößt den Hüter sofort an. Läuft schon eine Wache oder wird nicht gehandelt, startet er "
                    "nichts.")},
    {"schluessel": "nachtscan", "titel": "Nachtscan",
     "anstoss": "scanner.yml", "zustand": "scanner.yml", "echt_ab_s": 120,
     "knopf": "Nachtscan prüfen und bei Bedarf nachholen",
     "erklaerung": ("Der Nachtscan rechnet um 18:00 Uhr New Yorker Zeit, also gegen Mitternacht Wiener Zeit, "
                    "die Kaufpunkte der beiden Wochenlisten und der einzeln überwachten Aktien. Der Knopf scannt "
                    "nur, wenn der fällige Scan fehlt; ein geglückter Scan bleibt, wie er ist.")},
    {"schluessel": "tabelle", "titel": "Scanner-Tabelle",
     "anstoss": "scanner_daten.yml", "zustand": "scanner_daten.yml", "echt_ab_s": 120,
     "knopf": "Scanner-Tabelle prüfen und bei Bedarf bauen",
     "erklaerung": ("Die Scanner-Tabelle entsteht nach dem Nachtscan. Der Knopf baut nur, wenn sie nicht "
                    "schon mit dem neuesten Nachtscan rechnet.")},
)

ERGEBNIS = {"success": "erfolgreich", "failure": "fehlgeschlagen", "cancelled": "abgebrochen",
            "timed_out": "über die Zeitgrenze gelaufen und beendet", "skipped": "übersprungen",
            "startup_failure": "konnte nicht starten", "action_required": "wartet auf eine Freigabe",
            "neutral": "ohne Ergebnis", "stale": "veraltet"}
WARTEND = ("queued", "waiting", "pending", "requested")


def _zeit(text):
    """ISO-Zeit der GitHub-API als datetime in UTC, None wenn unlesbar."""
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def wien(dt):
    if dt is None:
        return None
    if ZoneInfo is not None:
        try:
            return dt.astimezone(ZoneInfo("Europe/Vienna"))
        except Exception:  # noqa
            pass
    return dt


def zeitpunkt_text(dt, jetzt=None, seit=False):
    """'am 18.09.2026 um 18:26 Uhr Wiener Zeit', mit seit 'seit dem 18.09.2026
    um ...': immer Tag, Monat und Jahr (Antwort 99 vom 24.09.2026). jetzt
    bleibt fuer die Aufrufer stehen."""
    w = wien(dt)
    return f"{'seit dem' if seit else 'am'} {w:%d.%m.%Y} um {w:%H:%M} Uhr Wiener Zeit"


def dauer_s(lauf):
    a = _zeit(lauf.get("run_started_at") or lauf.get("created_at"))
    e = _zeit(lauf.get("updated_at"))
    if a is None or e is None:
        return None
    return max(0.0, (e - a).total_seconds())


def dauer_text(sekunden):
    if sekunden is None:
        return "unbekannt lange"
    if sekunden < 60:
        return "weniger als eine Minute"
    minuten = int(round(sekunden / 60))
    if minuten < 60:
        return "eine Minute" if minuten == 1 else f"{minuten} Minuten"
    stunden, rest = divmod(minuten, 60)
    teil = "eine Stunde" if stunden == 1 else f"{stunden} Stunden"
    return teil + (f" {rest} Minuten" if rest else "")


def zustand_saetze(laeufe, ablauf, jetzt=None):
    """Saetze zum Zustand eines Ablaufs aus workflow_runs (neueste zuerst,
    wie die API sie liefert). Zeiten in Wiener Zeit."""
    jetzt = jetzt or datetime.now(timezone.utc)
    laeufe = sorted([l for l in (laeufe or []) if _zeit(l.get("created_at"))],
                    key=lambda l: _zeit(l.get("created_at")), reverse=True)
    if not laeufe:
        return ["Bisher kein Lauf gefunden."]
    s = []
    aktiv = [l for l in laeufe if l.get("status") == "in_progress"]
    wartend = [l for l in laeufe if l.get("status") in WARTEND]
    if aktiv:
        a = aktiv[0]
        s.append(f"Läuft gerade, {zeitpunkt_text(_zeit(a.get('run_started_at') or a.get('created_at')), jetzt, seit=True)}.")
    if wartend:
        w = wartend[0]
        s.append(f"Ein weiterer Lauf wartet {zeitpunkt_text(_zeit(w.get('created_at')), jetzt, seit=True)} auf einen "
                 "Rechner.")
    fertig = [l for l in laeufe if l.get("status") == "completed"]
    if fertig:
        f = fertig[0]
        erg = ERGEBNIS.get(f.get("conclusion"), f.get("conclusion") or "ohne Ergebnis")
        s.append(f"Letzter abgeschlossener Lauf {zeitpunkt_text(_zeit(f.get('run_started_at') or f.get('created_at')), jetzt)}"
                 f", {dauer_text(dauer_s(f))}: {erg}.")
        grenze = ablauf.get("echt_ab_s") or 0
        if grenze:
            echt = [l for l in fertig if (dauer_s(l) or 0) >= grenze]
            if echt and echt[0] is not f:
                e = echt[0]
                erg_e = ERGEBNIS.get(e.get("conclusion"), e.get("conclusion") or "ohne Ergebnis")
                s.append(f"Zuletzt wirklich gerechnet {zeitpunkt_text(_zeit(e.get('run_started_at') or e.get('created_at')), jetzt)}"
                         f", {dauer_text(dauer_s(e))}: {erg_e}. Die kurzen Läufe dazwischen haben "
                         "festgestellt, dass nichts zu tun war.")
            elif not echt:
                s.append("Unter den letzten Läufen hat keiner länger gerechnet; sie haben festgestellt, dass nichts "
                         "zu tun war.")
    return s


NICHT_ANGESTOSSEN = "Der Ablauf ließ sich nicht anstoßen; der Stand oben bleibt, wie er ist."


def anstoss_satz(status_code, jetzt=None):
    """(angenommen, einfacher Satz, technischer Grund oder None) zur Antwort
    auf POST .../dispatches: 204 (frueher) oder 200 (seit der Rueckgabe der
    Laufnummer) heissen angenommen. Den technischen Grund zeigt die App klein
    unter dem Satz (Antwort 102 vom 24.09.2026)."""
    jetzt = jetzt or datetime.now(timezone.utc)
    if status_code in (200, 204):
        return True, (f"Angestoßen {zeitpunkt_text(jetzt, jetzt)}. Der Ablauf prüft selbst, ob etwas zu tun ist; "
                      "der Stand oben zeigt es nach etwa einer Minute; drück dazu Stand neu laden."), None
    if status_code in (401, 403):
        return False, NICHT_ANGESTOSSEN, (f"GitHub hat den Anstoß mit Code {status_code} abgelehnt: Dem Token "
                                          "ABLAUF_TOKEN fehlt die Berechtigung für Abläufe, oder er gilt nicht mehr.")
    if status_code == 404:
        return False, NICHT_ANGESTOSSEN, "GitHub kennt diesen Ablauf nicht, Code 404."
    if status_code == 422:
        return False, NICHT_ANGESTOSSEN, ("GitHub hat den Anstoß mit Code 422 abgelehnt: Der Ablauf nimmt keinen "
                                          "Anstoß von Hand an.")
    return False, NICHT_ANGESTOSSEN, f"GitHub hat den Anstoß mit Code {status_code} nicht angenommen."


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest():
    fehler = []

    def p(name, ok, zusatz=""):
        print(("  ok   " if ok else "  FEHL ") + name + (f"; {zusatz}" if zusatz else ""))
        if not ok:
            fehler.append(name)

    jetzt = datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc)   # 16:00 Wien
    waechter = ABLAEUFE[0]
    scan = ABLAEUFE[1]
    laeufe_w = [
        {"status": "in_progress", "conclusion": None, "created_at": "2026-09-21T13:30:05Z",
         "run_started_at": "2026-09-21T13:30:20Z", "updated_at": "2026-09-21T13:59:00Z"},
        {"status": "completed", "conclusion": "cancelled", "created_at": "2026-09-18T16:20:00Z",
         "run_started_at": "2026-09-18T13:28:00Z", "updated_at": "2026-09-18T16:26:10Z"},
    ]
    s = zustand_saetze(laeufe_w, waechter, jetzt)
    p("Waechter: laufende Wache mit Wiener Zeit, letzter abgeschlossener Lauf mit Datum, Dauer und Ergebnis",
      s == ["Läuft gerade, seit dem 21.09.2026 um 15:30 Uhr Wiener Zeit.",
            "Letzter abgeschlossener Lauf am 18.09.2026 um 15:28 Uhr Wiener Zeit, 2 Stunden 58 Minuten: abgebrochen."],
      " | ".join(s))
    laeufe_s = [
        {"status": "completed", "conclusion": "success", "created_at": "2026-09-21T10:20:07Z",
         "run_started_at": "2026-09-21T10:20:10Z", "updated_at": "2026-09-21T10:20:40Z"},
        {"status": "completed", "conclusion": "success", "created_at": "2026-09-21T10:10:07Z",
         "run_started_at": "2026-09-21T10:10:10Z", "updated_at": "2026-09-21T10:10:35Z"},
        {"status": "completed", "conclusion": "success", "created_at": "2026-09-20T22:00:07Z",
         "run_started_at": "2026-09-20T22:00:12Z", "updated_at": "2026-09-20T22:31:40Z"},
    ]
    s2 = zustand_saetze(laeufe_s, scan, jetzt)
    p("Nachtscan: kurzer letzter Lauf, dazu der letzte, der wirklich gerechnet hat",
      s2 == ["Letzter abgeschlossener Lauf am 21.09.2026 um 12:20 Uhr Wiener Zeit, weniger als eine Minute: "
             "erfolgreich.",
             "Zuletzt wirklich gerechnet am 21.09.2026 um 00:00 Uhr Wiener Zeit, 31 Minuten: erfolgreich. Die kurzen Läufe "
             "dazwischen haben festgestellt, dass nichts zu tun war."], " | ".join(s2))
    s3 = zustand_saetze([laeufe_s[0]], scan, jetzt)
    p("Nachtscan: nur kurze Laeufe, ehrlich benannt",
      s3[-1].startswith("Unter den letzten Läufen hat keiner länger gerechnet"), " | ".join(s3))
    s4 = zustand_saetze([{"status": "queued", "conclusion": None, "created_at": "2026-09-21T13:58:00Z",
                          "updated_at": "2026-09-21T13:58:00Z"}], waechter, jetzt)
    p("Wartender Lauf wird benannt",
      s4 == ["Ein weiterer Lauf wartet seit dem 21.09.2026 um 15:58 Uhr Wiener Zeit auf einen Rechner."],
      " | ".join(s4))
    p("Keine Laeufe", zustand_saetze([], waechter, jetzt) == ["Bisher kein Lauf gefunden."])
    p("Unlesbare Zeiten fallen weg", zustand_saetze([{"status": "completed", "created_at": "kaputt"}], waechter, jetzt)
      == ["Bisher kein Lauf gefunden."])
    ok200, satz200, tech200 = anstoss_satz(200, jetzt)
    ok204, _s, _t = anstoss_satz(204, jetzt)
    ok403, satz403, tech403 = anstoss_satz(403, jetzt)
    p("Anstoss: 200 und 204 angenommen, 403 mit einfachem Satz und dem Grund klein darunter (Antwort 102)",
      ok200 and ok204 and not ok403 and tech200 is None and "ABLAUF_TOKEN" not in satz403
      and "ABLAUF_TOKEN" in tech403 and "am 21.09.2026 um 16:00 Uhr Wiener Zeit" in satz200,
      satz200 + " | " + satz403 + " | " + str(tech403))
    p("Hüter erklärt, Nachtscan nennt beide Wochenlisten und die einzeln überwachten (Antwort 75, Berichtigung 17)",
      "ein zweiter Ablauf, der alle sechs Minuten nachsieht, ob der Wächter läuft" in waechter["erklaerung"]
      and "der beiden Wochenlisten und der einzeln überwachten Aktien" in scan["erklaerung"])
    p("Dauer in Worten", dauer_text(59) == "weniger als eine Minute" and dauer_text(60) == "eine Minute"
      and dauer_text(3600) == "eine Stunde" and dauer_text(3720) == "eine Stunde 2 Minuten"
      and dauer_text(None) == "unbekannt lange")
    p("Jeder Ablauf hat Anstoss, Zustand, Knopf und Erklaerung",
      all(a["anstoss"].endswith(".yml") and a["zustand"].endswith(".yml") and a["knopf"] and a["erklaerung"]
          for a in ABLAEUFE))
    texte = [a["knopf"] + a["erklaerung"] + a["titel"] for a in ABLAEUFE] + list(ERGEBNIS.values()) \
        + s + s2 + s3 + s4 + [satz200, satz403, tech403]
    p("Keine Gedankenstriche und keine Bildzeichen in den Texten",
      not any(z in t for t in texte for z in ("–", "—")) and
      not any(ord(z) >= 0x2600 for t in texte for z in t))
    print()
    print("Alles bestanden." if not fehler else f"{len(fehler)} FEHLER.")
    return 0 if not fehler else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Saetze zum Zustand der Ablaeufe, die die App anstossen darf.")
    ap.add_argument("--selbsttest", action="store_true")
    args = ap.parse_args()
    if args.selbsttest:
        return selbsttest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
