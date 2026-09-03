# -*- coding: utf-8 -*-
"""Kontingent- und Funktionsprobe bei Groq fuer die Websuche der KI-Abfrage.

Frage 1: Zaehlt eine Anfrage an groq/compound-mini (Websuche) gegen das
Tageskontingent des Grundmodells openai/gpt-oss-120b, das der Podcatcher nutzt?
Frage 2: Mit welcher Anfrageform antwortet compound ueberhaupt (der erste Versuch
bekam 413 Request Entity Too Large bei einer winzigen Frage)?

Je Variante drei Anfragen: gpt-oss-120b (Kopfzeilen A), die Variante (Kopfzeilen
C), gpt-oss-120b (Kopfzeilen B). Sinkt die Restmenge der Anfragen je Tag von A
nach B nur um eins, zaehlt die Variante nicht mit. Der Schluessel wird nie
ausgegeben. Nur im Actions-Lauf (Secret GROQ_API_KEY)."""
import json
import os
import sys
import time

GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
KOPF = ("x-ratelimit-limit-requests", "x-ratelimit-remaining-requests", "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-tokens", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens")

FRAGE_SUCHE = ("Welche Schlagzeile gab es in den letzten Tagen zur Apple-Aktie? Nenne eine Quelle mit Datum, "
               "hoechstens 60 Woerter, auf Deutsch.")
FRAGE_OHNE = "Antworte nur mit OK."

VARIANTEN = [
    ("groq/compound-mini", FRAGE_OHNE, 50, None),
    ("groq/compound-mini", FRAGE_SUCHE, 2000, None),
    ("groq/compound-mini", FRAGE_SUCHE, 2000, {"tools": [{"type": "web_search"}]}),
    ("groq/compound", FRAGE_SUCHE, 2000, None),
]


def anfrage(modell, auftrag, max_tokens, extra=None):
    import messung_8k as m8k
    koerper = {"model": modell, "messages": [{"role": "user", "content": auftrag}]}
    if max_tokens:
        koerper["max_completion_tokens"] = max_tokens
    if extra:
        koerper.update(extra)
    t0 = time.time()
    status, kopf, roh = m8k._anfrage("https://api.groq.com/openai/v1/chat/completions", koerper, key=GROQ_KEY)
    k = {str(a).lower(): b for a, b in (kopf or {}).items()}
    werte = {n: k.get(n) for n in KOPF}
    inhalt, usage, werkzeuge = "", None, []
    if status == 200:
        a = json.loads(roh)
        nachricht = a["choices"][0]["message"]
        inhalt = (nachricht.get("content") or "")[:600]
        usage = a.get("usage")
        for w in nachricht.get("executed_tools") or []:
            werkzeuge.append({"typ": w.get("type"), "eingabe": str(w.get("arguments") or w.get("input") or "")[:200]})
    return {"modell": modell, "status": status, "dauer_s": round(time.time() - t0, 1), "kopf": werte,
            "usage": usage, "werkzeuge": werkzeuge, "antwort": inhalt, "fehler": None if status == 200 else roh[:400]}


def zahl(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def main():
    if not GROQ_KEY:
        print("GROQ_API_KEY fehlt (Secret im Actions-Lauf).")
        return 1
    erfolg = False
    for modell, frage, max_tokens, extra in VARIANTEN:
        print(f"=== Variante {modell}, max_completion_tokens {max_tokens}, extra {extra}, Frage: {frage[:50]}")
        a = anfrage("openai/gpt-oss-120b", FRAGE_OHNE, 5)
        time.sleep(3)
        c = anfrage(modell, frage, max_tokens, extra)
        time.sleep(3)
        b = anfrage("openai/gpt-oss-120b", FRAGE_OHNE, 5)
        print("C:", json.dumps(c, ensure_ascii=False))
        ra, rb = zahl(a["kopf"]["x-ratelimit-remaining-requests"]), zahl(b["kopf"]["x-ratelimit-remaining-requests"])
        if ra is not None and rb is not None:
            print(f"Befund Kontingent: gpt-oss-120b Anfragen je Tag vorher {ra}, nachher {rb}, Abzug {ra - rb} "
                  f"(1 = compound zaehlt NICHT mit, 2 oder mehr = zaehlt mit); compound-Status {c['status']}")
        else:
            print("Befund Kontingent: Restmenge nicht lesbar.")
        if c["status"] == 200:
            erfolg = True
        time.sleep(3)
    return 0 if erfolg else 1


if __name__ == "__main__":
    sys.exit(main())
