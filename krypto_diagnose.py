"""Erreichbarkeit der Krypto-Boersen-APIs, lokal und aus der Cloud.

WARUM (27.08.2026, Gerhards Krypto-Vorschlag): Gerhard schlaegt Binance
als Hauptfeed vor. Unsere gesamte Infrastruktur laeuft aber auf
GitHub-Rechnern, und die stehen in den USA (gemessen: Azure westus).
Mehrere grosse Boersen sperren US-Adressen komplett. Ob der Vorschlag
auf unserer Infrastruktur ueberhaupt laufen kann, ist deshalb eine
Messfrage, keine Meinungsfrage.

Geprueft werden die oeffentlichen REST-Zeitendpunkte (kein Schluessel,
kein Konto); wer die sperrt, sperrt auch die WebSocket-Streams
desselben Hauses. Ausgabe je Boerse: HTTP-Status und bei Fehlern der
Anfang der Antwort (dort steht die Sperrbegruendung).
"""

import sys

import requests

ENDPUNKTE = [
    ("Binance global", "https://api.binance.com/api/v3/ping"),
    ("Binance US", "https://api.binance.us/api/v3/ping"),
    ("Coinbase Exchange", "https://api.exchange.coinbase.com/time"),
    ("Kraken", "https://api.kraken.com/0/public/Time"),
    ("Bybit", "https://api.bybit.com/v5/market/time"),
    ("OKX", "https://www.okx.com/api/v5/public/time"),
    ("KuCoin", "https://api.kucoin.com/api/v1/timestamp"),
]


def main():
    frei, gesperrt = [], []
    for name, url in ENDPUNKTE:
        try:
            r = requests.get(url, timeout=20,
                             headers={"User-Agent": "heliot-diagnose/1.0"})
            status = r.status_code
            hinweis = ""
            if status != 200:
                text = r.text[:120].replace("\n", " ").strip()
                hinweis = f"; Antwort: {text}"
            print(f"  {name}: HTTP {status}{hinweis}")
            (frei if status == 200 else gesperrt).append(name)
        except Exception as e:
            print(f"  {name}: FEHLER {type(e).__name__}: {e}")
            gesperrt.append(name)
    print(f"\nErreichbar: {', '.join(frei) if frei else 'keine'}")
    print(f"Gesperrt oder gestoert: {', '.join(gesperrt) if gesperrt else 'keine'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
