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

5. STUMME WERTE GEBEN IHREN PLATZ AB. Nachgemessen am 28.07.2026
   (feedpruefung.py): Der Gratis-Strom deckt nicht jede Aktie ab.
   Vodafone und Ovintiv wurden im Messfenster nachweislich gehandelt und
   kamen trotzdem mit null Ticks an. Wer schweigt, blockiert sonst einen
   der nur 50 Plaetze fuer immer. Die STUFE aendert sich dadurch NICHT —
   eine stumme Aktie bleibt in Stufe 1 und wird genauso ueberwacht, sie
   bekommt ihre Kurse nur von yfinance statt tickweise. Es geht allein um
   die Platzvergabe.
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
        self._stumm = set()       # liefern keine Ticks (siehe Punkt 5)

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
        (siehe Punkt 3 im Modulkopf). Auch die Stummliste wird geleert:
        Abdeckung kann sich aendern, und ein Wert, der gestern schwieg,
        soll heute wieder eine Gelegenheit bekommen. Der Irrtum kostet
        hoechstens zwei Runden."""
        self._stufe = {}
        self._stumm = set()

    def merke_stumm(self, ticker_liste):
        """Diese Werte liefern trotz Abo keine Ticks — Platz freigeben."""
        neu = {t.upper() for t in ticker_liste} - self._stumm
        self._stumm |= neu
        return sorted(neu)

    @property
    def stumme(self):
        return sorted(self._stumm)

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

        # Stumme Werte bekommen keinen Platz am Strom (Punkt 5). Sie
        # BLEIBEN in ihrer Stufe — nur die Abo-Liste laesst sie aus, und
        # der frei gewordene Platz geht an den naechsten Anwaerter.
        ws_kandidaten = [t for t in stufe1 if t not in self._stumm]
        frei = max(0, self.max_ws - len(ws_kandidaten))
        vorraum_frei = [t for t in stufe2 if t not in self._stumm]
        oberer_vorraum = vorraum_frei[:frei]
        # Der 'rest_vorraum' ist die REST-Liste: Alles aus Stufe 2, das
        # nicht am Strom haengt — die Stummen ausdruecklich eingeschlossen,
        # sonst fielen sie zwischen die Quellen.
        mit_strom = set(oberer_vorraum)
        rest_vorraum = [t for t in stufe2 if t not in mit_strom]

        return {
            "stufe1": stufe1,
            "stufe2": stufe2,
            "stufe3": stufe3,
            "websocket": ws_kandidaten + oberer_vorraum,
            "rest_vorraum": rest_vorraum,
            "langsam": stufe3,
            "stumm": sorted(self._stumm & set(stufe1 + stufe2)),
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

    # 8) Stumme Werte geben ihren Platz ab — der Fall Vodafone/Ovintiv.
    # Gemessen am 28.07.2026: beide wurden gehandelt, kamen im Gratis-Strom
    # aber mit null Ticks an. Ihr Platz muss an den nächsten gehen, ihre
    # ÜBERWACHUNG darf sich dadurch nicht ändern.
    st.neu_aufbauen()
    voll = {f"T{i:03d}": 0.0004 * i for i in range(1, 46)}
    voll.update({f"V{i:03d}": 0.02 + 0.001 * i for i in range(1, 31)})
    vorher = st.aktualisiere(voll)
    belegt = len(vorher["websocket"])
    assert "T001" in vorher["websocket"]

    st.merke_stumm(["T001", "T002"])
    nachher = st.aktualisiere(voll)
    assert "T001" not in nachher["websocket"], "Stumme dürfen keinen Platz belegen"
    assert "T001" in nachher["stufe1"], \
        "die Stufe darf sich NICHT ändern — nur die Kursquelle"
    assert len(nachher["websocket"]) == belegt, \
        "die frei gewordenen Plätze müssen nachbesetzt werden"
    assert nachher["stumm"] == ["T001", "T002"]
    print(f"✓ Stumme Werte: 2 verlieren den Platz, bleiben aber in Stufe 1 — "
          f"die Liste ist weiter voll ({belegt} Plätze)")

    # Ein stummer Wert aus dem Vorraum darf nicht zwischen die Quellen
    # fallen: kein Strom, also gehört er in die REST-Liste.
    st.merke_stumm(["V001"])
    d = st.aktualisiere(voll)
    assert "V001" not in d["websocket"] and "V001" in d["rest_vorraum"], \
        "ein stummer Vorraum-Wert muss über REST versorgt werden"
    print("✓ Ein stummer Vorraum-Wert fällt nicht zwischen die Quellen")

    st.neu_aufbauen()
    assert st.stumme == [], "bei Eröffnung bekommt jeder wieder eine Chance"
    print("✓ Bei Eröffnung wird die Stummliste geleert")

    print("\nAlle Staffelungs-Tests bestanden (ohne Netzwerk, ohne Börse).")
