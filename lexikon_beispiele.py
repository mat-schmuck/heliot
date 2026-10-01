# -*- coding: utf-8 -*-
"""
DIE BEISPIELE DES LEXIKONS (Gerhard, 29.09.2026, Teil 3 b: "jeweils mit kurzem
Beispiel")
================================================================================
Je Feld des Scanners, je Strategie, je Template, je Einstellung des Scanners
und je Sektor ein kurzes Beispiel mit Zahlen. Wo viele Felder nach demselben
Bauplan gehen (Abstand zu Hoch und Tief, Abstand zu den Linien, Revisionen,
Einstufungen, Enge, Performance-Rang), baut feld_beispiel() das Beispiel aus
den Angaben des Felds, damit jedes trotzdem seine eigenen Worte bekommt.

Die Zahlen der Beispiele sind von Hand nachgerechnet (01.10.2026) und passen
zu den Schwellen dieses Tages; die Gesamtpruefung (Block D) haelt die
Schwellen fest, auf denen sie beruhen. Der Selbsttest in lexikon.py prueft,
dass jedes Feld, jede Strategie und jedes Template ein Beispiel hat.
"""

# ---------------------------------------------------------------------------
# Felder des Scanners, die kein Bauplan abdeckt
# ---------------------------------------------------------------------------

FELDER = {
    # Wachstum von Umsatz und Gewinn
    "umsatz_q": "Umsatz im jüngsten Quartal 120 Millionen Dollar, im selben Quartal des Vorjahres 100 Millionen: plus 20 "
                "Prozent.",
    "umsatz_q1": "Das Quartal davor brachte 110 Millionen Dollar Umsatz, dasselbe Quartal ein Jahr früher 88 Millionen: "
                 "plus 25 Prozent.",
    "umsatz_q2": "Zwei Quartale vor dem jüngsten 96 Millionen Dollar Umsatz, ein Jahr früher 80 Millionen: plus 20 "
                 "Prozent.",
    "umsatz_j": "Die letzten vier Quartale brachten 450 Millionen Dollar Umsatz, die vier Quartale davor 360 Millionen: "
                "plus 25 Prozent.",
    "umsatz_s": "Jüngstes Quartal 121 Millionen Dollar Umsatz, das Quartal davor 110 Millionen: plus 10 Prozent.",
    "eps_q": "Gewinn je Aktie im jüngsten Quartal 0,60 Dollar, im Vorjahresquartal 0,40 Dollar: plus 50 Prozent. War der "
             "Vorjahreswert minus 0,10 Dollar, steht hier nicht berechenbar.",
    "eps_q1": "Gewinn je Aktie im Quartal davor 0,55 Dollar, ein Jahr früher 0,44 Dollar: plus 25 Prozent.",
    "eps_q2": "Gewinn je Aktie zwei Quartale davor 0,50 Dollar, ein Jahr früher 0,25 Dollar: plus 100 Prozent.",
    "eps_j": "Gewinn je Aktie der letzten vier Quartale 2,10 Dollar, der vier Quartale davor 1,50 Dollar: plus 40 "
             "Prozent.",
    "eps_s": "Gewinn je Aktie im jüngsten Quartal 0,66 Dollar, im Quartal davor 0,60 Dollar: plus 10 Prozent.",
    "umsatz_cagr3": "Umsatz vor drei Geschäftsjahren 100 Millionen Dollar, heute 172,8 Millionen: im Schnitt plus 20 "
                    "Prozent pro Jahr.",
    "umsatz_cagr5": "Umsatz vor fünf Geschäftsjahren 100 Millionen Dollar, heute 161 Millionen: im Schnitt plus 10 "
                    "Prozent pro Jahr.",
    "eps_cagr3": "Gewinn je Aktie vor drei Geschäftsjahren 1,00 Dollar, heute 1,33 Dollar: im Schnitt plus 10 Prozent "
                 "pro Jahr.",
    "eps_stabilitaet": "Ein Wert von 5 heißt, der Gewinn je Aktie wächst Quartal für Quartal fast gleichmäßig; 80 heißt, "
                       "er springt stark auf und ab.",
    "rule40": "Umsatzwachstum 30 Prozent und FCF-Marge 15 Prozent ergeben 45: Rule of 40 erfüllt. 25 Prozent Wachstum "
              "bei minus 5 Prozent Marge ergäben 20.",
    "tage_zahlen": "Die Firma berichtete am Dienstag nachbörslich, die Aktie reagierte am Mittwoch; am Freitag steht "
                   "hier 2.",
    # Margen, Renditen und Cashflow
    "marge": "Umsatz 100 Millionen Dollar, Bruttogewinn 60 Millionen: Bruttomarge 60 Prozent.",
    "marge_q": "Bruttomarge jetzt 60 Prozent, im Vorjahresquartal 55 Prozent: plus 5 Prozentpunkte.",
    "marge_j": "Bruttomarge der letzten vier Quartale 58 Prozent, der vier Quartale davor 56 Prozent: plus 2 "
               "Prozentpunkte.",
    "marge_s": "Bruttomarge jetzt 60 Prozent, im Quartal davor 61 Prozent: minus 1 Prozentpunkt.",
    "marge_op_q": "Umsatz 100 Millionen Dollar, operatives Ergebnis 15 Millionen: operative Marge 15 Prozent.",
    "marge_vst_q": "Umsatz 100 Millionen Dollar, Ergebnis vor Steuern 13 Millionen: Vorsteuermarge 13 Prozent.",
    "marge_netto_q": "Umsatz 100 Millionen Dollar, Nettogewinn 10 Millionen: Nettomarge 10 Prozent.",
    "marge_brutto_fy": "Jahresumsatz 400 Millionen Dollar, Bruttogewinn 230 Millionen: Bruttomarge 57,5 Prozent.",
    "marge_op_fy": "Jahresumsatz 400 Millionen Dollar, operatives Ergebnis 60 Millionen: 15 Prozent.",
    "marge_vst_fy": "Jahresumsatz 400 Millionen Dollar, Ergebnis vor Steuern 52 Millionen: 13 Prozent.",
    "marge_netto_fy": "Jahresumsatz 400 Millionen Dollar, Nettogewinn 40 Millionen: 10 Prozent.",
    "roe": "Nettogewinn 40 Millionen Dollar, Eigenkapital 200 Millionen: Eigenkapitalrendite 20 Prozent.",
    "roa": "Nettogewinn 40 Millionen Dollar, Bilanzsumme 800 Millionen: 5 Prozent.",
    "roic": "Operatives Ergebnis 100 Millionen Dollar, Steuersatz 20 Prozent, eingesetztes Kapital 400 Millionen: 80 "
            "durch 400, also 20 Prozent.",
    "steuersatz": "Ergebnis vor Steuern 50 Millionen Dollar, Steuern 10,5 Millionen: Steuersatz 21 Prozent.",
    "umsatz_12m": "Die letzten vier Quartale brachten 120, 115, 110 und 105 Millionen Dollar: 450 Millionen Dollar.",
    "fcf": "Operativer Cashflow 80 Millionen Dollar, Investitionen 30 Millionen: Free Cashflow 50 Millionen Dollar.",
    "fcf_marge": "Free Cashflow 50 Millionen Dollar bei 400 Millionen Umsatz: FCF-Marge 12,5 Prozent.",
    "cash_conversion": "Operativer Cashflow 48 Millionen Dollar, Nettogewinn 40 Millionen: 1,2; der Gewinn kommt "
                       "vollständig als Geld herein.",
    "ausschuettung": "Nettogewinn 40 Millionen Dollar, gezahlte Dividenden 10 Millionen: Ausschüttungsquote 25 Prozent.",
    "sbc": "Umsatz 400 Millionen Dollar, aktienbasierte Vergütung 20 Millionen: 5 Prozent.",
    "ffo": "Ein Immobilienfonds mit 100 Millionen Dollar Nettogewinn und 60 Millionen Abschreibungen auf Gebäude kommt "
           "auf rund 160 Millionen Dollar FFO.",
    "ffo_je_aktie": "160 Millionen Dollar FFO bei 80 Millionen Aktien: 2 Dollar je Aktie.",
    # Kurs, Groesse und Aktienzahl
    "kurs": "Schließt die Aktie bei 42,50 Dollar, steht hier 42,5; eine Grenze von 15 schließt alle Aktien unter 15 "
            "Dollar aus.",
    "marktkap": "100 Millionen Aktien zu 30 Dollar sind 3 Milliarden Dollar Börsenwert; im Feld steht 3. Eine Grenze von "
                "0,7 heißt 700 Millionen Dollar.",
    "aktien": "Eine Firma mit 85 Millionen ausstehenden Aktien steht mit 85 da.",
    "aktien_1j": "Vor einem Jahr 100 Millionen Aktien, heute 104 Millionen: plus 4 Prozent, also Verwässerung.",
    "aktien_3j": "Vor drei Jahren 100 Millionen Aktien, heute 92 Millionen: minus 8 Prozent, die Firma hat zurückgekauft.",
    "streubesitz": "Laut Jahresbericht waren Aktien für 2,5 Milliarden Dollar im freien Handel: 2.500.",
    "historie": "Eine Aktie, die vor einem halben Jahr an die Börse kam, hat rund 126 Handelstage Kurshistorie.",
    # Volumen
    "volumen": "Im Schnitt der letzten 50 Handelstage wurden 1,2 Millionen Stück je Tag gehandelt: 1.200.000.",
    "vol50_10t": "Der 50-Tage-Schnitt liegt heute bei 1,1 Millionen Stück, vor 10 Handelstagen lag er bei 1 Million: "
                 "plus 10 Prozent.",
    "umsatz_dollar": "Im Schnitt 1 Million Stück zu 40 Dollar je Tag: 40 Millionen Dollar Tagesumsatz.",
    "tag_volumen": "Am letzten Handelstag wechselten 2,4 Millionen Aktien den Besitzer: 2.400.000.",
    "vol_min_3": "Die letzten drei Tage brachten 800.000, 650.000 und 900.000 Stück: Hier steht 650.000.",
    "vol_hoeher": "Gestern 900.000 Stück, heute 1,3 Millionen: erfüllt.",
    "vol_faktor": "Schnitt der 50 Handelstage davor 1 Million Stück, letzter Handelstag 2,5 Millionen: plus 150 Prozent "
                  "über dem 50-Tage-Schnitt.",
    "rvol_heute": "Um 11:00 Uhr New Yorker Zeit sind 600.000 Stück gehandelt, üblich sind bis dahin 30 Prozent des "
                  "Tages; hochgerechnet 2 Millionen Stück, bei 1 Million Schnitt plus 100 Prozent.",
    "dollarvol_heute": "Hochgerechnet 2 Millionen Stück zu 50 Dollar: 100 Millionen Dollar.",
    "vol_erste15": "Tagesschnitt der 20 Tage davor 1 Million Stück, in den ersten 15 Minuten wurden 400.000 gehandelt: "
                   "40 Prozent.",
    "vol_erste20": "In den ersten 20 Minuten 1,2 Millionen Stück bei 1 Million Tagesschnitt: 120 Prozent, mehr als ein "
                   "ganzer üblicher Tag.",
    "vol63": "Im Schnitt der letzten 63 Handelstage 900.000 Stück je Tag: 900.000.",
    "dv20": "Im Schnitt der letzten 20 Handelstage 1,5 Millionen Stück zu 30 Dollar: 45 Millionen Dollar.",
    "vdu": "Schnitt der 50 Handelstage davor 1 Million Stück, die letzten 10 Tage im Schnitt 600.000: minus 40 Prozent, "
           "das Volumen trocknet aus.",
    "vol5_20": "Die letzten 5 Tage im Schnitt 700.000 Stück, die letzten 20 Tage 1 Million: minus 30 Prozent.",
    "vol_spitze": "Der größte Tag der letzten 10 brachte 3 Millionen Stück bei 1 Million Schnitt: plus 200 Prozent.",
    "ud50": "In den letzten 50 Tagen 30 Millionen Stück an Plus-Tagen und 20 Millionen an Minus-Tagen: 1,5.",
    "volmax": "Das größte Volumen der ganzen Kurshistorie gab es vor 12 Handelstagen: 12.",
    "vol_max_12m": "Im Jahr vor dem letzten Handelstag lag der größte Tag bei 4 Millionen Stück: 4.000.000.",
    "rekord_1j": "Heute 5 Millionen Stück, der größte Tag des Jahres davor 4 Millionen: erfüllt.",
    "rekord_zahlen": "Seit der Reaktion auf die letzten Zahlen lag kein Tag über 3 Millionen Stück, heute sind es 3,5 "
                     "Millionen: erfüllt.",
    "rekord_ipo": "Heute wird mehr gehandelt als an jedem Tag seit dem ersten Kurs, auch mehr als am Tag des "
                  "Börsengangs: erfüllt.",
    "rekord_alle": "Heute ein Rekord seit einem Jahr, aber nicht seit dem Börsengang: erfüllt, weil eine der Arten "
                   "genügt.",
    # Letzter Handelstag
    "veraenderung": "Vortag 50 Dollar, letzter Schluss 52 Dollar: plus 4 Prozent.",
    "seit_open": "Eröffnung bei 50 Dollar, Schluss bei 51,50 Dollar: plus 3 Prozent seit der Eröffnung.",
    "rtg": "Vortagesschluss 40 Dollar, Eröffnung 39,20 Dollar, Schluss 40,80 Dollar: Red to Green.",
    "spanne": "Tagestief 48 Dollar, Tageshoch 51 Dollar: Spanne 6,25 Prozent.",
    "luecke": "Vortagesschluss 50 Dollar, Eröffnung 53 Dollar: Lücke plus 6 Prozent.",
    "pivot": "Vortagesschluss 20 Dollar, Eröffnung 23 Dollar: Lücke 15 Prozent, Episodic Pivot erfüllt.",
    "burst": "Vortag 30 Dollar und 400.000 Stück, heute Schluss 31,50 Dollar bei 650.000 Stück: plus 5 Prozent, Momentum "
             "Burst.",
    "schlusslage": "Tief 48 Dollar, Hoch 52 Dollar, Schluss 51 Dollar: 75.",
    "vortag": "Vorletzter Schluss 49 Dollar, der Schluss davor 50 Dollar: minus 2 Prozent.",
    "vortag_spanne": "Am Vortag Hoch 51 Dollar und Tief 49 Dollar: 4,1 Prozent.",
    "vortagesspanne": "Vortag zwischen 48 und 52 Dollar, letzter Schluss 53 Dollar: 125, also über dem Vortageshoch.",
    "oops": "Vortagestief 40 Dollar, heute Eröffnung bei 39,50 Dollar: erfüllt.",
    "spy_tag": "Der SPY schloss gestern bei 500 Dollar und heute bei 495 Dollar: minus 1 Prozent, bei jeder Aktie "
               "derselbe Wert.",
    "qqq_tag": "Der QQQ steigt von 450 auf 459 Dollar: plus 2 Prozent.",
    # Volatilitaet und Schwankung
    "adr": "Liegt das Tageshoch im Mittel der letzten 20 Tage 5 Prozent über dem Tagestief, ist die ADR 5.",
    "vola5": "Die letzten fünf Tage schwankten im Mittel 3 Prozent zwischen Tief und Hoch: 3.",
    "vola21": "Im letzten Monat lag das Hoch im Mittel 4 Prozent über dem Tief: 4.",
    "atr": "Eine Aktie schwankt samt Lücken im Schnitt 2 Dollar am Tag: ATR 2.",
    "atr_pct": "ATR 2 Dollar bei einem Kurs von 50 Dollar: 4 Prozent.",
    "atr_verh": "ATR der letzten 5 Tage 1,50 Dollar, der letzten 50 Tage 2 Dollar: 0,75, die Aktie wird ruhiger.",
    "atr14_10t": "ATR 14 heute 1,80 Dollar, vor 10 Handelstagen 2 Dollar: minus 10 Prozent.",
    "beta": "Steigt der SPY um 1 Prozent und die Aktie im Mittel um 1,5 Prozent, ist das Beta 1,5.",
    "jahresspanne": "52-Wochen-Tief 20 Dollar, 52-Wochen-Hoch 50 Dollar: 2,5.",
    # Gleitende Durchschnitte und Trend
    "ema8_21": "EMA 8 bei 52 Dollar, EMA 21 bei 50 Dollar, Schluss 53 Dollar: erfüllt.",
    "sma50_200": "SMA 50 bei 60 Dollar, SMA 200 bei 52 Dollar: erfüllt.",
    "sma200_10t": "SMA 200 heute 51 Dollar, vor 10 Handelstagen 50 Dollar: plus 2 Prozent, die Linie steigt.",
    "ma200_steigt": "Die 200-Tage-Linie ist an den letzten 35 Handelstagen jeden Tag gestiegen: 35.",
    "ti65": "Schnitt der letzten 7 Schlüsse 105 Dollar, der letzten 65 Schlüsse 100 Dollar: 1,05.",
    "weinstein": "Die 30-Wochen-Linie steigt, und die letzten zwei Wochenschlüsse liegen darüber: Stufe 2.",
    "linie30_steig": "Die 30-Wochen-Linie stand vor vier Wochen bei 50 Dollar und heute bei 52 Dollar: plus 4 Prozent.",
    # Abstand von Hoch und Tief
    "tage_hoch_1j": "Das 52-Wochen-Hoch fiel vor drei Handelstagen: 3. Von 0 bis 5 findet alle Aktien mit einem "
                    "52-Wochen-Hoch in der letzten Woche.",
    "tage_tief_1j": "Das 52-Wochen-Tief liegt 200 Handelstage zurück: 200.",
    "neu_52w": "Das höchste Hoch der 52 Wochen davor lag bei 80 Dollar, heute erreicht die Aktie 81 Dollar: erfüllt.",
    "neu_ath": "Das bisherige Allzeithoch lag bei 150 Dollar, heute erreicht die Aktie 151 Dollar: erfüllt.",
    # Wertentwicklung und Momentum
    "perf_1w": "Schluss vor 5 Handelstagen 48 Dollar, heute 50 Dollar: plus 4,2 Prozent.",
    "perf_1m": "Schluss vor 21 Handelstagen 40 Dollar, heute 50 Dollar: plus 25 Prozent.",
    "perf_40t": "Schluss vor 40 Handelstagen 25 Dollar, heute 50 Dollar: plus 100 Prozent.",
    "perf_60t": "Schluss vor 60 Handelstagen 30 Dollar, heute 45 Dollar: plus 50 Prozent.",
    "perf_3m": "Schluss vor 63 Handelstagen 50 Dollar, heute 60 Dollar: plus 20 Prozent.",
    "perf_6m": "Schluss vor 126 Handelstagen 50 Dollar, heute 75 Dollar: plus 50 Prozent.",
    "perf_12m": "Schluss vor einem Jahr 40 Dollar, heute 60 Dollar: plus 50 Prozent.",
    "perf_ytd": "Letzter Schluss des Vorjahres 50 Dollar, heute 55 Dollar: plus 10 Prozent.",
    "rsi14": "Nach zwei Wochen fast nur mit Plus-Tagen steht der RSI 14 bei 78: überkauft.",
    "rsi2": "Nach zwei kräftigen Minus-Tagen fällt der RSI 2 auf 5: eine kurze Übertreibung nach unten.",
    # Relative Staerke
    "rs": "RS 92 heißt: Die Aktie war in den letzten zwölf Monaten stärker als 92 Prozent aller US-Aktien.",
    "rs_1w": "Vor einer Woche RS 85, heute 91: plus 6 Punkte.",
    "rs_4w": "Vor vier Wochen RS 70, heute 88: plus 18 Punkte.",
    "mrs": "Die RS-Linie gegen SPY liegt 8 Prozent über ihrem 52-Wochen-Schnitt: Mansfield RS plus 8.",
    "mrs_vorher": "Vor vier Wochen lag der Mansfield RS bei minus 2, heute bei plus 8: Er steigt.",
    "rs_linie": "Die Aktie fällt mit dem Markt, aber weniger stark, und ihre Linie gegen SPY erreicht ein 52-Wochen-Hoch: "
                "erfüllt.",
    "rs_linie_qqq": "Dieselbe Rechnung gegen den Nasdaq-100-ETF QQQ: Kurs geteilt durch QQQ auf dem 52-Wochen-Hoch, erfüllt.",
    "rs_linie_abst": "Die RS-Linie gegen SPY steht 4 Prozent unter ihrem 52-Wochen-Hoch: 4; auf dem Hoch steht 0.",
    "rs_linie_qqq_abst": "Die RS-Linie gegen QQQ steht 2 Prozent unter ihrem 52-Wochen-Hoch: 2.",
    "rs_linie_1w": "Die Aktie steigt in einer Woche 5 Prozent, der SPY 1 Prozent: Die Linie steigt um rund 4 Prozent.",
    "rs_linie_qqq_1w": "Die Aktie fällt in einer Woche 1 Prozent, der QQQ 3 Prozent: Die Linie steigt um rund 2 Prozent.",
    # Ratings
    "eps_rating": "Eine Firma, deren Gewinn je Aktie seit Jahren stärker wächst als bei 90 Prozent der übrigen Firmen, "
                  "kommt auf rund 90.",
    "smr": "Starkes Umsatzwachstum, hohe Margen und eine Eigenkapitalrendite von 25 Prozent ergeben etwa 85, Note A.",
    "ad": "Schließt eine Aktie seit Wochen meist nahe dem Tageshoch bei hohem Volumen, liegt ihr A/D-Rang hoch, etwa "
          "bei 85, Note A.",
    "composite": "Hohes EPS-Rating und RS, gute Ratings und die Nähe zum Hoch ergeben einen Composite von 95.",
    "tt_count": "Erfüllt eine Aktie alles außer einem RS von mindestens 70, steht hier 7.",
    # Bilanz und Sicherheit
    "schulden_ek": "Finanzschulden 100 Millionen Dollar, Eigenkapital 200 Millionen: 0,5.",
    "lt_schulden_ek": "Langfristige Finanzschulden 60 Millionen Dollar, Eigenkapital 200 Millionen: 0,3.",
    "schulden_vermoegen": "Finanzschulden 100 Millionen Dollar bei 800 Millionen Bilanzsumme: 12,5 Prozent.",
    "ek_quote": "Eigenkapital 200 Millionen Dollar bei 800 Millionen Bilanzsumme: 25 Prozent.",
    "fk_quote": "Verbindlichkeiten 600 Millionen Dollar bei 800 Millionen Bilanzsumme: 75 Prozent.",
    "current_ratio": "Umlaufvermögen 300 Millionen Dollar, kurzfristige Verbindlichkeiten 150 Millionen: 2.",
    "quick_ratio": "Umlaufvermögen 300 Millionen Dollar, davon 100 Millionen Vorräte, kurzfristige Verbindlichkeiten "
                   "150 Millionen: 200 durch 150, also 1,33.",
    "zinsdeckung": "Operatives Ergebnis 50 Millionen Dollar, Zinsen 5 Millionen: 10, die Zinsen sind zehnmal verdient.",
    "schulden": "Kurzfristige Kredite 20 Millionen Dollar und Anleihen 80 Millionen: 100 Millionen Dollar.",
    "nettoschulden": "Finanzschulden 100 Millionen Dollar, Kasse 150 Millionen: minus 50, also 50 Millionen Dollar "
                     "Nettokasse.",
    "fscore": "Gewinn, steigender Cashflow, sinkende Schulden und bessere Margen ergeben zusammen 7 der 9 Signale: 7.",
    "altman_z": "Ein Wert von 3,5 liegt in der sicheren Zone, 1,5 in der Gefahrenzone.",
    "kernkapital": "Eine Bank mit 12 Milliarden Dollar Kernkapital und 100 Milliarden risikogewichteten Aktiva: 12 "
                   "Prozent.",
    "risikovorsorge": "Eine Bank hat für 50 Milliarden Dollar Kredite 1 Milliarde zurückgelegt: 2 Prozent.",
    "einlagen": "Kundeneinlagen vor einem Jahr 40 Milliarden Dollar, heute 42 Milliarden: plus 5 Prozent.",
    # Bewertung
    "kgv": "Börsenwert 3 Milliarden Dollar, Nettogewinn der letzten vier Quartale 100 Millionen: KGV 30.",
    "kuv": "Börsenwert 3 Milliarden Dollar, Umsatz der letzten zwölf Monate 600 Millionen: KUV 5.",
    "kbv": "Börsenwert 3 Milliarden Dollar, Eigenkapital 1 Milliarde: KBV 3.",
    "ev": "Börsenwert 3.000 Millionen Dollar plus 500 Millionen Schulden minus 200 Millionen Kasse: 3.300 Millionen "
          "Dollar.",
    "ev_ebitda": "Enterprise Value 3.300 Millionen Dollar, operatives Ergebnis plus Abschreibungen 300 Millionen: 11.",
    "ev_umsatz": "Enterprise Value 3.300 Millionen Dollar, Umsatz 1.100 Millionen: 3.",
    "peg": "KGV 30 bei 30 Prozent Gewinnwachstum: PEG 1; bei 15 Prozent Wachstum wäre es 2.",
    "p_ffo": "Kurs 40 Dollar, FFO je Aktie 2,50 Dollar: 16.",
    "fcf_rendite": "Free Cashflow 150 Millionen Dollar bei 3 Milliarden Börsenwert: 5 Prozent.",
    "div_rendite": "Dividenden 60 Millionen Dollar bei 3 Milliarden Börsenwert: 2 Prozent.",
    "rueckkauf": "Rückkäufe für 90 Millionen Dollar bei 3 Milliarden Börsenwert: 3 Prozent.",
    "cash_je_aktie": "Kasse und kurzfristige Anlagen 500 Millionen Dollar bei 100 Millionen Aktien: 5 Dollar.",
    "nettokasse_je_aktie": "500 Millionen Dollar Kasse minus 200 Millionen Schulden bei 100 Millionen Aktien: 3 Dollar.",
    "buchwert_je_aktie": "Eigenkapital 1 Milliarde Dollar bei 100 Millionen Aktien: 10 Dollar.",
    "fcf_je_aktie": "Free Cashflow 150 Millionen Dollar bei 100 Millionen Aktien: 1,50 Dollar.",
    # Analysten und Konsens
    "konsens": "Empfehlen die meisten Analysten Kaufen, steht der Konsens bei 4; eine Grenze ab 4 findet Aktien mit "
               "Kaufen oder starkem Kauf.",
    "analysten_anzahl": "Zwölf Analysten geben eine Empfehlung ab: 12.",
    "kaufanteil": "9 von 12 Analysten raten zum Kauf: 75 Prozent.",
    "kursziel": "Mittleres Kursziel 60 Dollar, Kurs 50 Dollar: plus 20 Prozent.",
    "kursziel_tief": "Niedrigstes Kursziel 45 Dollar, Kurs 50 Dollar: minus 10 Prozent.",
    "kursziel_hoch": "Höchstes Kursziel 80 Dollar, Kurs 50 Dollar: plus 60 Prozent.",
    "fwd_kgv": "Kurs 60 Dollar, erwarteter Gewinn je Aktie im nächsten Geschäftsjahr 3 Dollar: 20.",
    "kgv_0y": "Kurs 60 Dollar, erwarteter Gewinn je Aktie im laufenden Geschäftsjahr 2,40 Dollar: 25.",
    "eps_erwartet": "Laufendes Geschäftsjahr 2,40 Dollar je Aktie, nächstes erwartet 3 Dollar: plus 25 Prozent.",
    "umsatz_erwartet": "Laufendes Geschäftsjahr 500 Millionen Dollar Umsatz, nächstes erwartet 600 Millionen: plus 20 "
                       "Prozent.",
    "beat": "In drei der letzten vier Quartale lag der Gewinn über der Schätzung: 3.",
    "ueberraschung": "Erwartet waren 0,50 Dollar je Aktie, gemeldet 0,60 Dollar: plus 20 Prozent.",
    # Leerverkaeufe
    "short_anteil": "Von 2 Millionen außerbörslich gemeldeten Stück waren 900.000 Leerverkäufe: 45 Prozent.",
    "short_anteil_fenster": "Über 20 Handelstage waren 40 Prozent des gemeldeten Volumens Leerverkäufe: 40.",
    "short_tage": "An 18 der letzten 20 Handelstage gab es außerbörsliche Umsätze: 18.",
    # Branchengruppe
    "gruppe_rang": "Die Halbleiter-Gruppe ist die drittstärkste aller Gruppen: Rang 3.",
    "gruppe_rang_3w": "Vor drei Wochen stand die Gruppe auf Rang 25, heute auf Rang 3: Sie steigt schnell.",
    "gruppe_rang_6w": "Vor sechs Wochen Rang 60, vor drei Wochen 25, heute 3: ein stetiger Aufstieg.",
    "gruppe_titel": "Von 30 Aktien der Gruppe haben 24 ein volles RS und gehen in den Rang ein: 24.",
}

# Die Zeitraeume der Revisionen, im Akkusativ mit Artikel
PERIODE_AKK = {"0q": "das laufende Quartal", "1q": "das nächste Quartal", "0y": "das laufende Geschäftsjahr",
               "1y": "das nächste Geschäftsjahr"}
_ZEITRAUM = {"perf_rang_1m": "einem Monat", "perf_rang_3m": "drei Monaten", "perf_rang_6m": "sechs Monaten"}


def feld_beispiel(feld) -> str:
    """Das Beispiel eines Felds des Scanners: aus FELDER oder nach Bauplan."""
    s = feld.schluessel
    if s in FELDER:
        return FELDER[s]
    if feld.bezug and s.startswith("hoch"):
        return (f"Liegt das {feld.bezug} bei 50 Dollar und der Schluss bei 45 Dollar, steht hier 10; am Hoch steht 0.")
    if feld.bezug and s.startswith("tief"):
        return f"Liegt das {feld.bezug} bei 40 Dollar und der Schluss bei 50 Dollar, steht hier 25."
    if feld.linie:
        return (f"Liegt die {feld.linie} bei 50 Dollar und der Schluss bei 52 Dollar, steht hier plus 4; bei 48 Dollar "
                "minus 4.")
    if s.startswith("rmv_"):
        n = s.split("_")[1]
        return (f"Ist die Aktie heute so eng wie an keinem der letzten {n} Handelstage, steht hier 0; ein Wert unter "
                "15 gilt als eng.")
    if s in _ZEITRAUM:
        return (f"Stieg eine Aktie in {_ZEITRAUM[s]} stärker als 97 Prozent aller Aktien der Tabelle, steht hier 97.")
    if s.startswith("rev_"):
        teile = s.split("_")
        art, tage, periode = teile[1], teile[2].rstrip("t"), PERIODE_AKK.get(teile[3], "den Zeitraum")
        if art == "hoch":
            return f"Drei Analysten heben in den letzten {tage} Tagen ihre Gewinnschätzung für {periode} an: 3."
        if art == "runter":
            return f"Ein Analyst senkt in den letzten {tage} Tagen seine Gewinnschätzung für {periode}: 1."
        return (f"Vor {tage} Tagen erwarteten die Analysten für {periode} 2,00 Dollar Gewinn je Aktie, heute 2,10 "
                "Dollar: plus 5 Prozent.")
    if s.startswith("stufen_"):
        tage = s.rsplit("_", 1)[1].rstrip("t")
        art = s[len("stufen_"):].rsplit("_", 1)[0]
        return {"hoch": f"Zwei Analysten stufen die Aktie in den letzten {tage} Tagen herauf, etwa von Halten auf "
                        "Kaufen: 2.",
                "runter": f"Ein Analyst stuft die Aktie in den letzten {tage} Tagen von Kaufen auf Halten herab: 1.",
                "neu": f"Drei Häuser bewerten die Aktie in den letzten {tage} Tagen zum ersten Mal: 3.",
                "ziel_rauf": f"Vier Analysten heben in den letzten {tage} Tagen ihr Kursziel für die Aktie an: 4.",
                "ziel_runter": f"Ein Analyst senkt in den letzten {tage} Tagen sein Kursziel für die Aktie: 1."}.get(art, "")
    return ""


# ---------------------------------------------------------------------------
# Strategien (Schluessel aus einstellungen.ALARME)
# ---------------------------------------------------------------------------

STRATEGIEN = {
    "htf": "Eine Aktie steigt in 30 Handelstagen von 20 auf 42 Dollar und pendelt danach zwei Wochen zwischen 38 und 42 "
           "Dollar: Kaufpunkt 42,01 Dollar, Stop 37,99 Dollar.",
    "htf_innen": "In der Flagge zwischen 38 und 42 Dollar bleibt ein Tag zwischen 40 und 41 Dollar: Kaufpunkt 41,01 "
                 "Dollar, Stop 39,99 Dollar, früher und mit kleinerem Risiko als über der ganzen Flagge.",
    "vcp": "Rücksetzer von 25, 12 und 6 Prozent, jedes Mal mit weniger Volumen, der letzte zwischen 47 und 50 Dollar: "
           "Pivot 50 Dollar, Kaufpunkt 50,01 Dollar.",
    "cup": "Eine Tasse fällt von 60 auf 45 Dollar, 25 Prozent tief, und steigt rund zurück; der Henkel pendelt zwischen "
           "56 und 60 Dollar: Kaufpunkt knapp über 60 Dollar, Ziel 75 Dollar.",
    "cup_woche": "Eine Tasse über 40 Wochen fällt von 100 auf 55 Dollar, 45 Prozent tief, mit einem Henkel zwischen 90 "
                 "und 100 Dollar: Kaufpunkt knapp über 100 Dollar.",
    "darvas": "Neues 52-Wochen-Hoch bei 50 Dollar, danach drei Tage darunter als Deckel und drei Tage mit dem Boden bei "
              "46 Dollar: Kaufpunkt 50,01 Dollar, Stop 45,99 Dollar.",
    "earnings": "Nach starken Zahlen eröffnet eine Aktie 12 Prozent höher bei 56 Dollar; danach fünf ruhige Tage "
                "zwischen 55 und 58 Dollar: Kaufpunkt 58,01 Dollar, Stop 4 Prozent unter 55 Dollar, also 52,80 Dollar.",
    "ema": "Die Aktie erobert die 10- und die 20-Tage-Linie zurück, setzt eine Woche später zum ersten Mal an sie zurück "
           "und schließt mit einem Umkehrtag darüber, Hoch 41 Dollar: Kaufpunkt 41,01 Dollar.",
    "rechteck": "Eine Aktie pendelt sechs Wochen zwischen 42 und 46 Dollar und berührt beide Kanten zweimal; der Kurs "
                "liegt über dem 21-Tage-Durchschnitt: Kaufpunkt 46,01 Dollar, Stop 41,99 Dollar, Ziel 50 Dollar.",
    "shakeout": "Eine Aktie im Aufwärtstrend fällt kurz unter ihre Unterstützung bei 30 Dollar und schließt am selben "
                "Tag bei 31 Dollar; eine Woche später testet sie die Zone mit weniger Volumen und hält: Kaufpunkt über "
                "der Oberkante der Zone.",
    "crash": "Der S&P 500 steht 15 Prozent unter seinem Hoch; ein großes, gesundes Unternehmen hält an seiner "
             "Unterstützungszone: Es steht im Logbuch, eine Meldung gibt es nicht.",
    "fb_52w": "52-Wochen-Hoch 80 Dollar: Kaufpunkt 80,08 Dollar, Stop 74,40 Dollar.",
    "fb_20t": "Hoch der letzten 20 Handelstage 33 Dollar, Tief 30 Dollar: Kaufpunkt 33,01 Dollar, Stop 29,99 Dollar.",
    "fb_ma50p": "Kurs 55 Dollar, 50-Tage-Durchschnitt 50 Dollar: Kaufpunkt 50,25 Dollar, Stop 47,50 Dollar.",
    "fb_ma50r": "Kurs 47 Dollar, 50-Tage-Durchschnitt 50 Dollar: Kaufpunkt 50,25 Dollar, Stop 47 Dollar.",
    "fb_63t": "Hoch der letzten 63 Handelstage 70 Dollar: Kaufpunkt 70,01 Dollar, Stop 8 Prozent darunter bei 64,41 "
              "Dollar.",
    "a_3wt": "Nach einem Anstieg von 60 auf 80 Dollar schließen drei Wochen bei 80,10, 80,40 und 80,20 Dollar; das "
             "höchste Wochenhoch liegt bei 81 Dollar: Kaufpunkt 81,10 Dollar.",
    "a_inside": "Drei steigende Tage, dann ein Tag zwischen 49 und 51 Dollar innerhalb des Vortags von 48 bis 52 Dollar: "
                "enger Einstieg bei 51 Dollar, konservativer Einstieg bei 52 Dollar.",
    "a_pocket": "Der größte Abwärtstag der letzten zehn Tage hatte 900.000 Stück; heute steigt die Aktie über ihrer SMA "
                "50 mit 1,4 Millionen Stück auf ein Tageshoch von 45 Dollar: Einstieg über 45 Dollar.",
    "a_ipo": "Eine Aktie geht bei 40 Dollar an die Börse, steigt auf 60 Dollar und fällt in vier Wochen auf 42 Dollar, "
             "30 Prozent tief: Kaufpunkt am linken Hoch plus 10 Cent, also 60,10 Dollar.",
    "a_shakeout3": "Hoch 100 Dollar, scharfer Abverkauf auf 80 Dollar: Einstieg bei 88 Dollar, 10 Prozent über dem "
                   "Tief; der Einstieg bei 5 Prozent läge bei 84 Dollar.",
    "a_wick": "Die Aktie eröffnet bei 50,30 Dollar, fällt im Handel bis an die EMA 21 bei 48 Dollar und schließt bei "
              "50,50 Dollar nahe dem Hoch von 50,80 Dollar: Kaufpunkt 50,90 Dollar.",
    "r2g": "Der Nasdaq eröffnet schwach; eine Aktie der Fokusliste eröffnet bei 39,50 Dollar unter dem Vortagesschluss "
           "von 40 Dollar und steigt mit kräftigem Volumen auf 40,20 Dollar: Kaufmeldung, Stop 40 Dollar.",
    "r2gx": "Eine Aktie der Fokusliste eröffnet 2 Prozent unter dem Vortagesschluss und dreht aus eigener Kraft ins Plus, "
            "während der Nasdaq steigt: Red to Green Explosive.",
    "gapgo": "Eine Aktie springt nach Zahlen von 40 auf 44 Dollar, das Tief bleibt bei 43 Dollar, Schluss bei 46 Dollar "
             "nahe dem Hoch von 46,50 Dollar, Volumen plus 300 Prozent: Meldung am Lückentag. Am nächsten Tag liegt der "
             "Kaufpunkt knapp über 46,50 Dollar.",
    "insider": "Der Vorstandschef kauft für 6 Millionen Dollar Aktien seiner Firma; oder drei Direktoren kaufen binnen "
               "zehn Tagen je für 300.000 Dollar: Bericht Insider-Käufe.",
}

# ---------------------------------------------------------------------------
# Templates bekannter Trader (Kennungen aus scanner_ansicht.TEMPLATES)
# ---------------------------------------------------------------------------

TEMPLATES = {
    "kell_bull_snort": "Eine Aktie über 20 Dollar mit 800.000 Stück Schnitt steigt heute 3 Prozent bei plus 150 Prozent "
                       "Volumen: Treffer.",
    "kell_52w": "Eine Aktie über 20 Dollar mit Beta 1,4 und 800.000 Stück Schnitt macht heute ein neues "
                "52-Wochen-Hoch: Treffer.",
    "kell_gappers": "Eine Aktie über 20 Dollar mit 800.000 Stück Schnitt eröffnet 4 Prozent über dem Vortagesschluss: "
                    "Treffer.",
    "kell_doublers": "Eine Aktie über 20 Dollar stand zum Jahresende bei 30 Dollar und heute bei 65 Dollar, plus 117 "
                     "Prozent: Treffer.",
    "kell_fundies": "Eine Aktie über 20 Dollar, 5 Prozent unter ihrem 52-Wochen-Hoch, Gewinn je Aktie plus 30 Prozent, "
                    "Umsatz plus 25 Prozent, Eigenkapitalrendite 18 Prozent: Treffer.",
    "kell_down_days": "Der SPY fällt um 1,5 Prozent, eine Aktie über 20 Dollar mit Beta 1,3 schließt im Plus: Treffer.",
    "qm_ep": "Eine Aktie eröffnet 15 Prozent höher und handelt in den ersten 20 Minuten mehr als ein ganzes übliches "
             "Tagesvolumen: Treffer.",
    "qm_ep_weit": "Eine Aktie steigt um 9 Prozent, schließt über dem Vortageshoch und setzt heute hochgerechnet 150 "
                  "Millionen Dollar um: Treffer.",
    "qm_top_1m": "Eine Aktie mit 20 Millionen Dollar Dollarvolumen und 5 Prozent ADR stieg im letzten Monat stärker als "
                 "98 Prozent aller Aktien: Treffer.",
    "qm_top_3m": "Eine Aktie mit 20 Millionen Dollar Dollarvolumen und 5 Prozent ADR stieg in drei Monaten stärker als "
                 "99 Prozent aller Aktien: Treffer.",
    "qm_top_6m": "Eine Aktie mit 20 Millionen Dollar Dollarvolumen und 5 Prozent ADR stieg in sechs Monaten stärker als "
                 "97 Prozent aller Aktien: Treffer.",
    "qm_continuation": "Eine Aktie stieg im letzten Monat um 30 Prozent, schwankt mit 5 Prozent ADR und liegt 1 Prozent "
                       "über ihrer SMA 10: Treffer.",
    "qm_ipos": "Eine Aktie, seit 300 Handelstagen an der Börse, mit 5 Millionen Dollar Dollarvolumen: Treffer.",
    "sb_4pct": "Eine Aktie steigt 5 Prozent bei höherem Volumen als gestern, 400.000 Stück, und schließt bei 80 Prozent "
               "ihrer Tagesspanne: Treffer.",
    "sb_momentum": "Eine Aktie mit TI65 von 1,08, 25 Prozent über der SMA 126 und 120 Prozent über dem 52-Wochen-Tief: "
                   "Treffer.",
    "sb_anticipation": "Eine Aktie über 3 Dollar mit TI65 von 1,06 schließt heute fast unverändert, plus 0,2 Prozent, "
                       "und handelt an jedem der letzten drei Tage über 100.000 Stück: Treffer.",
    "sb_ep9": "Eine Aktie über 3 Dollar handelt heute 12 Millionen Stück; im ganzen Jahr davor nie mehr als 6 Millionen: "
              "Treffer.",
    "sb_magna": "Umsatz plus 40 und plus 35 Prozent in den letzten zwei Quartalen, heute eine Lücke von 6 Prozent, "
                "Börsenwert 2 Milliarden Dollar, seit acht Jahren an der Börse: Treffer.",
    "soreide_htf": "Eine Aktie verdoppelt sich in 40 Handelstagen, liegt über SMA 50 und SMA 200, und Schwankung wie "
                   "Volumen nehmen zuletzt ab: Treffer.",
    "rai_rekord": "Eine Aktie handelt heute so viel wie nie seit ihrem Börsengang und schließt im Plus: Treffer.",
    "moglen_eng": "Eine Aktie mit einer Enge über 15 Tage von 8, Performance-Rang drei Monate 93, 1 Prozent über der EMA "
                  "21 und schrumpfendem Volumen: Treffer.",
    "jt_peg": "Eine Aktie reagiert heute auf Zahlen, steigt 14 Prozent bei plus 250 Prozent Volumen, die "
              "Gewinnüberraschung beträgt 30 Prozent: Treffer.",
    "jt_monster": "Eine Aktie springt am Tag nach den Zahlen 25 Prozent bei plus 400 Prozent Volumen: Treffer.",
    "walker_4040": "Eine Aktie über 10 Dollar, 8 Prozent unter dem 52-Wochen-Hoch, mit Gewinnwachstum von 45, 60 und 52 "
                   "Prozent in den letzten drei Quartalen: Treffer.",
    "walker_30eps": "Eine Aktie über 12 Dollar, 10 Prozent unter dem 52-Wochen-Hoch, Gewinn plus 35 Prozent, weder "
                    "Biotechnologie noch Versorger: Treffer.",
    "haber_rs": "Die RS-Linie steht auf dem 52-Wochen-Hoch, der Kurs hatte sein 52-Wochen-Hoch vor sechs Handelstagen: Treffer.",
    "oops": "Eine Aktie eröffnet unter dem Vortagestief bei 39,50 Dollar und schließt bei 40,50 Dollar in der "
            "Vortagesspanne von 40 bis 43 Dollar: Treffer.",
    "oops_stark": "Dieselbe Eröffnung unter dem Vortagestief, Schluss bei 42 Dollar über der Mitte der Vortagesspanne "
                  "von 40 bis 43 Dollar: Treffer.",
    "oops_super": "Eröffnung unter dem Vortagestief, Schluss bei 43,50 Dollar über dem Vortageshoch von 43 Dollar: "
                  "Treffer.",
}

# ---------------------------------------------------------------------------
# Einstellungen des Scanners (Schluessel wie oberflaeche.SCANNER_ERKLAERUNGEN)
# ---------------------------------------------------------------------------

SCANNER = {
    "strategie": "Wählt man Darvas Box, zeigt der Scan nur Aktien mit einer frischen Darvas-Box; ohne Wahl filtern nur "
                 "die Einstellungen in Teil 2.",
    "toleranz": "Mit 5 Prozent Toleranz zählt eine Tasse von 11,5 Prozent Tiefe noch, obwohl streng mindestens 12 "
                "Prozent verlangt sind; der Treffer bekommt dafür 5 Punkte weniger beim Rating.",
    "handelbar": "Eine Aktie zu 8 Dollar fällt heraus, ebenso eine mit 6 Millionen Dollar Tagesumsatz oder eine, die "
                 "erst seit einem halben Jahr an der Börse ist.",
    "langweilig": "Eine Aktie, deren 52-Wochen-Hoch nur 40 Prozent über dem 52-Wochen-Tief liegt, fällt mit ihrer Box heraus.",
    "rs_vorlaeufig": "Eine Aktie, seit acht Monaten an der Börse, hat ein vorläufiges RS von 94; mit dem Haken zählt sie "
                     "bei RS ab 90 mit.",
    "termine": "Mit dem Haken bei Zahlen heute nachbörslich findet der Scan alle Aktien, die heute nach Handelsschluss "
               "berichten.",
    "termine_heute_vor": "Eine Firma berichtet heute um 7:00 Uhr New Yorker Zeit: Sie gehört dazu.",
    "termine_heute_nach": "Eine Firma berichtet heute um 16:05 Uhr New Yorker Zeit: Sie gehört dazu.",
    "termine_morgen_vor": "Ist heute Donnerstag, gehören die Firmen dazu, die am Freitag vor Handelsbeginn berichten.",
    "termine_morgen_nach": "Ist heute Freitag, gehören die Firmen dazu, die am Montag nach Handelsschluss berichten.",
    "termine_ohne_zeit": "Eine Firma berichtet heute um 12:00 Uhr New Yorker Zeit, mitten im Handel: Sie zählt nur mit "
                         "diesem Haken.",
    "termine_umfang": "Mit Nur die Aktien der Wochenlisten zeigt der Filter nur die Zahlentermine der überwachten "
                      "Aktien.",
}

# Je Sektor ein Beispiel ohne Firmennamen
SEKTOREN = {
    "Basic Materials": "Ein Kupferminenbetreiber oder ein Chemiekonzern.",
    "Consumer Discretionary": "Ein Autohersteller, eine Hotelkette oder ein Onlinehändler.",
    "Consumer Staples": "Ein Lebensmittelkonzern oder ein Hersteller von Zahnpasta.",
    "Energy": "Ein Ölförderer oder ein Betreiber von Gasleitungen.",
    "Finance": "Eine Bank, eine Versicherung oder eine Börse.",
    "Health Care": "Ein Pharmakonzern, eine Biotechfirma oder ein Hersteller von Herzschrittmachern.",
    "Industrials": "Ein Flugzeugbauer, eine Eisenbahn oder ein Maschinenbauer.",
    "Miscellaneous": "Passt eine Aktie in keinen der zwölf übrigen Sektoren, steht sie hier.",
    "Real Estate": "Ein Immobilienfonds, der Bürogebäude vermietet.",
    "Technology": "Ein Chiphersteller oder ein Softwarehaus.",
    "Telecommunications": "Ein Mobilfunkanbieter oder ein Kabelnetzbetreiber.",
    "Utilities": "Ein Stromversorger oder ein Wasserwerk.",
    "": "Eine frisch notierte Aktie, zu der die Daten noch keinen Sektor nennen.",
}
