#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DREISTUFIGE LIVE-KURS-STAFFELUNG
=================================
Teil 3 aus Gerhards Ausbauplan — das Herzstueck. Aktien werden nach ihrer
NAEHE ZUM KAUFPUNKT einsortiert und je Stufe unterschiedlich schnell mit
Kursen versorgt. So bekommen nur die wirklich relevanten Werte teure
Echtzeit-Ticks, der Rest laeuft sparsam.

  Stufe 1  bis 2 %      Finnhub-WebSocket, tickweise          max 30
  Stufe 2  2 % bis 4 %  oberer Teil ebenfalls WebSocket,      max 100
                        Rest per REST alle 2 Minuten
  Stufe 3  ueber 4 %    yfinance alle 10 Minuten              alle uebrigen

Dieses Modul rechnet AUSSCHLIESSLICH die Zuteilung. Es holt keine Kurse
und verschickt nichts — das macht es pruefbar, ohne dass eine Boerse
offen sein muss.

Vier Dinge, die sauber geloest sein muessen (Gerhards Vorgaben plus die
Fallen, die beim Bau auffielen):

1. HYSTERESE GEGEN FLATTERN. Ein Wert, der genau auf einer Grenze
   pendelt, darf nicht staendig die Stufe wechseln — jeder Wechsel ist
   ein An- und Abmelden beim WebSocket. Aufstieg bei 2,0 %, Rueckstufung
   erst bei 2,5 %; Aufstieg in Stufe 2 bei 4,0 %, Rueckstufung bei 4,5 %.

2. DER VORRAUM IST DER SCHLUESSEL. Mit nur zwei Listen (schnell/langsam)
   wuerde eine Aktie, die neu in die 2-%-Zone eintritt, erst beim
   naechsten langsamen Takt bemerkt. Der Vorraum wird darum haeufiger
   geprueft, und sein oberer Teil haengt gleich mit am WebSocket.

3. BEI EROEFFNUNG KOMPLETT NEU RECHNEN. Beim Open springen Kurse per
   Luecke mitten in eine Zone, ohne sich durch die Stufen genaehert zu
   haben. Wer nur fortschreibt, verpasst das. neu_aufbauen() wirft
   deshalb das Hysterese-Gedaechtnis weg.

4. EINE FUEHRUNGSQUELLE JE AKTIE. Sieht Finnhub eine Aktie bei 1,9 %,
   yfinance aber bei 2,1 %, wanderte sie je nach Quelle in eine andere
   Stufe. Dieses Modul bekommt deshalb FERTIGE Abstaende uebergeben; der
   Aufrufer ist dafuer verantwortlich, sie je Aktie immer aus derselben
   Quelle zu bestimmen (config: datenquellen.abstand_fuehrungsquelle).

5. STUMME WERTE — WISSEN, NICHT HANDELN. Nachgemessen am 28.07.2026
   (feedpruefung.py): Der Gratis-Strom deckt nicht jede Aktie ab.
   Vodafone und Ovintiv wurden im Messfenster nachweislich gehandelt und
   kamen trotzdem mit null Ticks an. Eine Regel, die solche Werte nach 12
   Minuten hinauswirft, war kurz gebaut und wurde wieder entfernt: Im
   normalen Handel ist diese Frist viel zu lang, um zu helfen (Mathias,
   28.07.2026). Stattdessen bleiben zehn der 50 Plaetze als Puffer frei
   (config: websocket_max_werte = 40). Dieses Modul teilt also rein nach
   Abstand zu; wer stumm bleibt, taucht nur im Protokoll auf.
"""

from config import CFG


class Staffelung:
    """Fuehrt die Zuteilung samt Hysterese ueber die Zeit."""

    def __init__(self, cfg=None):
        c = cfg or CFG["staffelung"]
        self.rein1 = c["stufe1_max_pct"]
        self.raus1 = c["stufe1_raus_pct"]
        self.rein2 = c["stufe2_max_pct"]
        self.raus2 = c["stufe2_raus_pct"]
        self.max1 = c["stufe1_max_werte"]
        self.max2 = c["stufe2_max_werte"]
        self.max_ws = c.get("websocket_max_werte", 50)
        self._stufe = {}          # ticker -> zuletzt zugeteilte Stufe

    # -- Innereien -------------------------------------------------------

    def _neue_stufe(self, ticker, abstand):
        """Stufe MIT Hysterese: Wer drin ist, bleibt laenger drin."""
        alt = self._stufe.get(ticker)
        if alt == 1:
            if abstand <= self.raus1:
                return 1
        elif abstand <= self.rein1:
            return 1

        if alt in (1, 2):
            if abstand <= self.raus2:
                return 2
        elif abstand <= self.rein2:
            return 2
        return 3

    # -- Steuerung -------------------------------------------------------

    def neu_aufbauen(self):
        """Hysterese-Gedaechtnis verwerfen — bei Boersenoeffnung Pflicht
        (siehe Punkt 3 im Modulkopf)."""
        self._stufe = {}

    def aktualisiere(self, abstaende: dict) -> dict:
        """abstaende: {ticker: relativer Abstand zum Kaufpunkt}, wobei
        0.015 fuer 1,5 % steht. Negative Werte (Kurs schon ueber dem
        Kaufpunkt) zaehlen als Abstand 0 — naeher geht nicht.

        Liefert die fertige Aufteilung samt der Listen, die die
        Kursbeschaffung braucht."""
        bewertet = []
        for ticker, abstand in abstaende.items():
            if abstand is None:
                continue
            bewertet.append((max(0.0, float(abstand)), ticker.upper()))
        bewertet.sort()          # naechste zuerst

        stufe1, stufe2, stufe3 = [], [], []
        neu = {}
        for abstand, ticker in bewertet:
            s = self._neue_stufe(ticker, abstand)
            # Platzgrenzen: Wer keinen Platz mehr findet, rutscht eine
            # Stufe tiefer. Weil nach Abstand sortiert ist, gewinnen immer
            # die NAECHSTEN — genau die, auf die es ankommt.
            if s == 1 and len(stufe1) >= self.max1:
                s = 2
            if s == 2 and len(stufe2) >= self.max2:
                s = 3
            neu[ticker] = s
            (stufe1 if s == 1 else stufe2 if s == 2 else stufe3).append(ticker)
        self._stufe = neu

        # Die freien WebSocket-Plaetze bekommt der OBERE Vorraum: die
        # Werte knapp ueber 2 %, die am ehesten gleich hochkommen.
        frei = max(0, self.max_ws - len(stufe1))
        oberer_vorraum = stufe2[:frei]
        rest_vorraum = stufe2[frei:]

        return {
            "stufe1": stufe1,
            "stufe2": stufe2,
            "stufe3": stufe3,
            "websocket": stufe1 + oberer_vorraum,
            "rest_vorraum": rest_vorraum,
            "langsam": stufe3,
        }

    def stufe_von(self, ticker):
        return self._stufe.get(ticker.upper())


def abstand_zum_kaufpunkt(kurs, kaufpunkt):
    """Relativer Abstand nach OBEN bis zum Kaufpunkt.
    0.02 heisst: der Kurs muss noch 2 % steigen. Liegt er schon darueber,
    ist der Abstand 0."""
    if not kaufpunkt or kurs is None:
        return None
    return max(0.0, (kaufpunkt - kurs) / kaufpunkt)


if __name__ == "__main__":
    st = Staffelung()
    print(f"Grenzen: Stufe 1 rein bei {st.rein1*100:.1f} %, raus bei "
          f"{st.raus1*100:.1f} % | Stufe 2 rein {st.rein2*100:.1f} %, raus "
          f"{st.raus2*100:.1f} %")
    print(f"Plätze: Stufe 1 max {st.max1}, WebSocket gesamt {st.max_ws}\n")

    # 1) Grundzuteilung
    a = st.aktualisiere({"NAH": 0.01, "MITTE": 0.03, "FERN": 0.09})
    assert a["stufe1"] == ["NAH"] and a["stufe2"] == ["MITTE"] and a["stufe3"] == ["FERN"]
    print("✓ Grundzuteilung: 1 % → Stufe 1, 3 % → Vorraum, 9 % → langsam")

    # 2) Hysterese: knapp über der Rein-Grenze bleibt drin
    a = st.aktualisiere({"NAH": 0.022, "MITTE": 0.03, "FERN": 0.09})
    assert st.stufe_von("NAH") == 1, "2,2 % muss in Stufe 1 BLEIBEN (Hysterese)"
    a = st.aktualisiere({"NAH": 0.026, "MITTE": 0.03, "FERN": 0.09})
    assert st.stufe_von("NAH") == 2, "erst über 2,5 % darf zurückgestuft werden"
    print("✓ Hysterese: 2,2 % bleibt oben, erst 2,6 % stuft zurück — kein Flattern")

    # 3) Wieder rein erst bei 2,0 %, nicht schon bei 2,4 %
    a = st.aktualisiere({"NAH": 0.024, "MITTE": 0.03, "FERN": 0.09})
    assert st.stufe_von("NAH") == 2, "2,4 % darf noch NICHT wieder aufsteigen"
    a = st.aktualisiere({"NAH": 0.019, "MITTE": 0.03, "FERN": 0.09})
    assert st.stufe_von("NAH") == 1
    print("✓ Aufstieg erst wieder bei 2,0 %, nicht schon bei 2,4 %")

    # 4) Platzgrenze: die NÄCHSTEN gewinnen.
    # Bewusst 45 Aktien INNERHALB der 2 % — mehr, als Stufe 1 fasst. Der
    # erste Anlauf dieses Tests war zu lasch (nur 20 Werte unter 2 %), da
    # wurde die Grenze gar nicht erreicht und hätte nichts bewiesen.
    st.neu_aufbauen()
    viele = {f"T{i:03d}": 0.0004 * i for i in range(1, 46)}   # 0,04 % bis 1,8 %
    viele.update({f"V{i:03d}": 0.02 + 0.001 * i for i in range(1, 31)})  # Vorraum
    a = st.aktualisiere(viele)
    assert len(a["stufe1"]) == st.max1, \
        f"Stufe 1 muss bei {st.max1} gedeckelt sein, war {len(a['stufe1'])}"
    assert a["stufe1"][0] == "T001", "die nächste Aktie muss zuerst drin sein"
    assert "T045" not in a["stufe1"], "die entferntesten müssen rausfallen"
    assert "T045" in a["stufe2"], "Überzählige rutschen in den Vorraum, nicht ins Nichts"
    assert len(a["websocket"]) <= st.max_ws
    print(f"✓ Platzgrenze: {len(a['stufe1'])} von 45 Anwärtern in Stufe 1 "
          f"(die nächsten gewinnen), Überzählige rutschen in den Vorraum")

    # 5) Oberer Vorraum füllt die freien WebSocket-Plätze
    frei = st.max_ws - len(a["stufe1"])
    assert len(a["websocket"]) == len(a["stufe1"]) + min(frei, len(a["stufe2"]))
    print(f"✓ Oberer Vorraum belegt die {frei} freien Plätze — kein blinder "
          f"Fleck an der 2-%-Grenze")

    # 6) Eröffnung: Gedächtnis muss weg
    st.neu_aufbauen()
    assert st.stufe_von("T001") is None
    print("✓ Bei Eröffnung wird die Zuteilung komplett neu aufgebaut")

    # 7) Abstandsrechnung
    assert abs(abstand_zum_kaufpunkt(98.0, 100.0) - 0.02) < 1e-9
    assert abstand_zum_kaufpunkt(105.0, 100.0) == 0.0
    print("✓ Abstand: Kurs 98 zu Kaufpunkt 100 sind 2 %; schon darüber → 0 %")

    # 8) Der Puffer muss echt sein: Mit 40 statt 50 Plätzen (Mathias,
    # 28.07.2026) darf die Liste die harte Grenze von 50 nie erreichen,
    # auch nicht bei Andrang aus allen Stufen.
    st.neu_aufbauen()
    andrang = {f"T{i:03d}": 0.0004 * i for i in range(1, 46)}
    andrang.update({f"V{i:03d}": 0.02 + 0.001 * i for i in range(1, 61)})
    a = st.aktualisiere(andrang)
    assert len(a["websocket"]) == st.max_ws, \
        "bei Andrang müssen alle verfügbaren Plätze belegt sein"
    assert len(a["websocket"]) <= 50 - 5, \
        "der Puffer zur harten Finnhub-Grenze muss erhalten bleiben"
    print(f"✓ Puffer: {len(a['websocket'])} Plätze belegt, "
          f"{50 - len(a['websocket'])} bleiben zur harten Grenze frei")

    print("\nAlle Staffelungs-Tests bestanden (ohne Netzwerk, ohne Börse).")
