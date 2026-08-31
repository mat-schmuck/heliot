#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Einmal-Sonde fuer Gerhards Fundamentaldaten-Machbarkeitsstudie
(31.08.2026): Wie gross sind die SEC-Bulk-Archive, wie tief reicht die
XBRL-Historie je Firma, wie viele Filer gibt es? Nur Messung, baut
nichts auf. Braucht SEC_USER_AGENT (dasselbe Secret wie der
Insider-Scanner)."""

import json
import os
import sys
import urllib.request

UA = {"User-Agent": os.environ.get("SEC_USER_AGENT", "").strip()}


def kopf(url):
    req = urllib.request.Request(url, headers=UA, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            gr = r.headers.get("Content-Length")
            return int(gr) if gr else None
    except Exception as e:
        return f"FEHLER {type(e).__name__}: {e}"


def haupt():
    if not UA["User-Agent"]:
        print("SEC_USER_AGENT fehlt.")
        return 1

    print("=== SONDE 1: Bulk-Archive (Groessen per HEAD) ===")
    for name, url in [
        ("companyfacts.zip (alle XBRL-Fakten aller Filer, taeglich neu)",
         "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"),
        ("submissions.zip (alle Einreichungs-Metadaten)",
         "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"),
        ("Financial Statement Data Set 2026q2 (ein Quartal, alle Firmen)",
         "https://www.sec.gov/files/dera/data/financial-statement-data-sets/2026q2.zip"),
        ("Financial Statement Data Set 2020q1 (Anfang des Zielzeitraums)",
         "https://www.sec.gov/files/dera/data/financial-statement-data-sets/2020q1.zip"),
    ]:
        g = kopf(url)
        if isinstance(g, int):
            print(f"  {name}: {g/1e6:,.0f} MB")
        else:
            print(f"  {name}: {g}")

    print("\n=== SONDE 2: companyfacts je Firma (drei Proben) ===")
    for name, cik in [("Apple", "0000320193"), ("Valero", "0001035002"),
                      ("Rubrik (IPO 2024)", "0001943896")]:
        try:
            req = urllib.request.Request(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                roh = r.read()
            d = json.loads(roh)
            usg = d.get("facts", {}).get("us-gaap", {})
            punkte = 0
            juengst, aeltest = "", "9999"
            for fakt in usg.values():
                for einheit in fakt.get("units", {}).values():
                    for e in einheit:
                        punkte += 1
                        ende = str(e.get("end", ""))
                        if ende > juengst:
                            juengst = ende
                        if ende and ende < aeltest:
                            aeltest = ende
            print(f"  {name}: {len(roh)/1e6:.1f} MB JSON, "
                  f"{len(usg)} us-gaap-Tags, {punkte:,} Datenpunkte, "
                  f"Zeitraum {aeltest} bis {juengst}")
        except Exception as e:
            print(f"  {name}: FEHLER {type(e).__name__}: {e}")

    print("\n=== SONDE 3: Wie viele Filer gibt es? ===")
    try:
        req = urllib.request.Request(
            "https://www.sec.gov/files/company_tickers.json", headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        print(f"  company_tickers.json: {len(d):,} Ticker-CIK-Zuordnungen "
              f"(boersennotierte Operating Companies)")
    except Exception as e:
        print(f"  company_tickers.json: FEHLER {type(e).__name__}: {e}")

    print("\n=== SONDE 4: Frisch eingereichte 10-Q im Live-Strom ===")
    try:
        req = urllib.request.Request(
            "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
            "&type=10-Q&dateb=&owner=include&count=10&action=getcompany",
            headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
        print("  Filing-Suche erreichbar (dieselbe Mechanik wie der "
              "Insider-Live-Strom deckt 10-Q/10-K/8-K ab).")
    except Exception as e:
        print(f"  FEHLER {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(haupt())
