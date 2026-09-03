# -*- coding: utf-8 -*-
"""Kontingent-Probe bei Groq: Zaehlt eine Anfrage an groq/compound-mini (Websuche)
gegen das Kontingent des Grundmodells openai/gpt-oss-120b, das der Podcatcher
nutzt? Drei Mini-Anfragen: gpt-oss-120b (Kopfzeilen A), compound-mini (Kopfzeilen
C), gpt-oss-120b (Kopfzeilen B). Sinkt die Restmenge der Anfragen je Tag von A
nach B nur um eins, zaehlt compound nicht mit. Der Schluessel wird nie ausgegeben.
Nur im Actions-Lauf (Secret GROQ_API_KEY)."""
import json
import os
import sys
import time

GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
KOPF = ("x-ratelimit-limit-requests", "x-ratelimit-remaining-requests", "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-tokens", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens")


def anfrage(modell, auftrag, max_tokens):
    import messung_8k as m8k
    koerper = {"model": modell, "temperature": 0, "max_completion_tokens": max_tokens,
               "messages": [{"role": "user", "content": auftrag}]}
    t0 = time.time()
    status, kopf, roh = m8k._anfrage("https://api.groq.com/openai/v1/chat/completions", koerper, key=GROQ_KEY)
    k = {str(a).lower(): b for a, b in (kopf or {}).items()}
    werte = {n: k.get(n) for n in KOPF}
    inhalt, usage, werkzeuge = "", None, 0
    if status == 200:
        a = json.loads(roh)
        nachricht = a["choices"][0]["message"]
        inhalt = (nachricht.get("content") or "")[:400]
        usage = a.get("usage")
        werkzeuge = len(nachricht.get("executed_tools") or [])
    return {"modell": modell, "status": status, "dauer_s": round(time.time() - t0, 1), "kopf": werte,
            "usage": usage, "werkzeugaufrufe": werkzeuge, "antwort": inhalt, "fehler": None if status == 200 else roh[:300]}


def zahl(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def main():
    if not GROQ_KEY:
        print("GROQ_API_KEY fehlt (Secret im Actions-Lauf).")
        return 1
    a = anfrage("openai/gpt-oss-120b", "Antworte nur mit OK.", 5)
    print("A gpt-oss-120b:", json.dumps({k: v for k, v in a.items() if k != "antwort"}, ensure_ascii=False))
    time.sleep(3)
    c = anfrage("groq/compound-mini", "Suche im Netz: Welche Schlagzeile gab es heute zur Apple-Aktie? Nenne eine Quelle mit Datum, hoechstens 60 Woerter, auf Deutsch.", 400)
    print("C compound-mini:", json.dumps(c, ensure_ascii=False))
    time.sleep(3)
    b = anfrage("openai/gpt-oss-120b", "Antworte nur mit OK.", 5)
    print("B gpt-oss-120b:", json.dumps({k: v for k, v in b.items() if k != "antwort"}, ensure_ascii=False))
    ra, rb = zahl(a["kopf"]["x-ratelimit-remaining-requests"]), zahl(b["kopf"]["x-ratelimit-remaining-requests"])
    if ra is None or rb is None:
        print("Befund: Restmenge der Anfragen je Tag nicht lesbar.")
    else:
        diff = ra - rb
        print(f"Befund: Restmenge gpt-oss-120b Anfragen je Tag vorher {ra}, nachher {rb}, Abzug {diff} "
              f"(1 = nur die eigene Mini-Anfrage, compound zaehlt NICHT mit; 2 oder mehr = compound zaehlt mit).")
    ta, tb = zahl(a["kopf"]["x-ratelimit-remaining-tokens"]), zahl(b["kopf"]["x-ratelimit-remaining-tokens"])
    print(f"Tokens je Minute gpt-oss-120b: vorher {ta}, nachher {tb} (Minutenfenster, schwankt von selbst).")
    return 0 if c["status"] == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
