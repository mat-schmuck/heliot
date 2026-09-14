#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONFIG — zentrale Einstellungen für das GESAMTE System
======================================================
Alle Schwellwerte, Fensterlängen und Parameter an EINER Stelle. Jedes Modul
(Scanner, Wächter, Radar, Berichte) liest ausschließlich von hier.

Warum das der wichtigste Aufräumschritt ist:
  Vorher standen dieselben Werte an mehreren Stellen im Code — z. B. das
  Volumen-Fenster im Scanner UND im Wächter. Weichen die auseinander, rechnen
  zwei Module unbemerkt mit verschiedenen Zahlen. Das erzeugt Fehler, die
  niemand sieht, weil nichts abstürzt. Ab jetzt gibt es die Wahrheit nur hier.

Benutzung im Code:
  from config import CFG
  fenster = CFG["volumen"]["fenster_tage"]

Überschreiben per Umgebungsvariable (optional, für Tests):
  CFG-Werte lassen sich über ENV übersteuern, z. B. SCANNER_VOL_FENSTER=20
  (siehe _aus_env unten). So muss man zum Testen nichts im Code ändern.
"""

import os

# ---------------------------------------------------------------------------
# Zentrale Konfiguration — die EINZIGE Quelle der Wahrheit
# ---------------------------------------------------------------------------

CFG = {

    # --- Push-Sammler (Gerhards Go vom 02.09.2026) ---
    # Befund vom 31.08.2026 (ntfy-Zustellprotokoll): Der Waechter schickte
    # fuenf Pushes binnen EINER Sekunde (15:32:28), alle mit HTTP 200
    # angenommen, aber Mathias' iPhone zeigte nur einen Teil davon an.
    # Apples Push-Dienst fasst schnelle Serien zusammen und verwirft
    # einzelne Meldungen; damit gingen echte Signale verloren. Gerhard:
    # "Das heisst, ich verpasse gerade echte Signale. Dafuer gebe ich dir
    # hiermit sofort das Go." Zwischen zwei Pushes liegt seither ein
    # Mindestabstand; die Wartezeit sitzt VOR der Handelszeit-Sperre,
    # damit ein verzoegerter Push nie nach dem Schlussgong rausgeht.
    "push": {
        "mindestabstand_s": 10,
    },

    # --- Zahlen-Karenz (Gerhards Freigabe vom 31.08.2026) ---
    # Messgrundlage ist die Logbuch-Forensik vom 30.08.2026: Signale mit
    # Quartalstermin binnen sieben Tagen nach dem Trigger liefen im
    # Schnitt auf minus 3,38 Prozent bei 25 Prozent Stopp-Quote, alle
    # uebrigen auf minus 0,83 Prozent bei 11 Prozent; sechs der zehn
    # groessten Verlierer stuerzten an frischen Zahlen (ONON, LQDA
    # zweimal, KOD, RBRK, HWM).
    #
    # STUFE A seit 31.08.2026 abends (GERHARDS ENTSCHEID zu Frage G1,
    # ersetzt die am Vormittag gebaute Stufe B): Es wird ALLES gemeldet,
    # aber jede Meldung im Karenzfenster traegt einen harten Warnkopf
    # als vorderste Zeile (heute und morgen ueber die bestehenden
    # Termin-Hinweise, uebermorgen und der Montags-Fall am Freitag ueber
    # zahlen_termine.karenz_hinweis). Sein Wortlaut: "Ich will die
    # Signale sehen und selbst entscheiden, nicht dass das System sie
    # fuer mich wegfiltert. Die Warnung reicht mir, das Urteil bleibt
    # bei mir." Jeder Treffer im Fenster steht mit zahlen_karenz=true
    # im Logbuch, damit die Trefferquote im Fenster messbar bleibt.
    "zahlen_karenz": {
        # 2 heisst: Termin heute, morgen oder uebermorgen (Handelstage).
        # Die gemessenen Killer lagen bei plus 0 bis plus 2 Tagen.
        # Von Gerhard bestaetigt (Frage G2).
        "handelstage": 2,
        # Kapitel 7 und 9 bleiben AUSGENOMMEN (Frage G3, bestaetigt):
        # Red-to-Green ist ein Tagesgeschaeft am selben Tag, und der
        # Luecken-Bestaetigungstag IST oft die Zahlen-Reaktion selbst.
        # Bei Stufe A wirkt das von selbst: Beide Kapitel melden ueber
        # eigene Formatierer, die den Karenz-Warnkopf nie anhaengen. Die
        # Liste "ausgenommen" stand bis 13.09.2026 hier; gelesen hat sie
        # kein Modul (Etappe 0, Gerhard 13.09.2026).
    },

    # --- Earnings-Pullback (Gerhards Freigabe vom 31.08.2026) ---
    # Baustein 2 des Einbau-Papiers: Nach starken Quartalszahlen wird
    # nicht der Sprung gekauft, sondern der Ausbruch aus der ersten
    # engen Konsolidierung darueber. Literatur: PEAD (Bernard/Thomas
    # 1989/1990), Power Earnings Gap (TraderStewie), Buyable Gap-Up
    # (Morales/Kacher). G4, G6 und G7 hat Gerhard am 31.08.2026 abends
    # bestaetigt; zu G5 hat er entschieden: Der TERMIN GENUEGT, auch
    # eine negative Ueberraschung lehnt nicht mehr ab ("lieber mehr
    # sehen und selbst filtern"). Feinjustierung nach den ersten
    # Logbuch-Wochen.
    "earnings_pullback": {
        "suchfenster_tage": 15,      # so weit zurueck wird nach dem Gap gesucht
        "min_gap_open": 0.08,        # G4: Eroeffnung 8 % ueber Vortagesschluss …
        "min_gap_close": 0.10,       # … ODER Schluss 10 % darueber
        "vol_faktor": 3.0,           # und Volumen >= 3x Ø10 davor
        "min_konsolidierung": 2,     # G6: 2 bis 15 Handelstage Konsolidierung
        "max_konsolidierung": 15,
        "max_spanne_anteil": 0.5,    # Spanne <= halbe Gap-Tag-Spanne
        # G7 in Gerhards Bestaetigungs-Wortlaut vom 31.08.2026: "4
        # Prozent Puffer unter dem Konsolidierungstief, weiter durch den
        # Zehn-Prozent-Deckel begrenzt". Die zuerst gebaute
        # Gap-Tief-Fassung war durch die Maximum-Bildung wirkungslos,
        # siehe detect_earnings_pullback.
        "porosity": 0.04,            # 4 % unter dem Konsolidierungstief
    },

    # --- EMA Crossback (GERHARDS ENTSCHEID vom 31.08.2026 abends, G11:
    # "DOCH BAUEN UND SCHARF SCHALTEN", mit der Bedingung, dass die
    # Ruecksetzer-Logik ausschliesslich in diesem Kapitel lebt — siehe
    # ema_crossback.py, dort steht, wie die Kapselung eingehalten wird).
    # Kells Stufe 3: Kauf ueber dem Umkehrtag-Hoch des ersten
    # Ruecksetzers an die 10er/20er-Linie nach frischer Rueckeroberung.
    "ema_crossback": {
        "min_historie": 40,          # weniger Tage: keine Aussage
        "pop_fenster_tage": 10,      # so frisch muss die Rueckeroberung sein
        "abwaerts_mindesttage": 3,   # echte Abwaertsphase vor dem Pop
        "kontakt_fenster_tage": 3,   # Linien-Kontakt in den letzten N Tagen
    },

    # --- Kell-Zyklus (Gerhards Freigabe vom 31.08.2026, nur Messung) ---
    # Baustein 5, Teil 1: Der Nachtscan klassifiziert je Aktie die
    # Phase in Oliver Kells Cycle of Price Action (10er/20er-EMA) und
    # schreibt sie als Feld in jede Logbuch-Zeile. Gefiltert wird
    # NICHTS — erst die Auswertung "Trefferquote je Phase" nach einigen
    # Wochen entscheidet, ob die Phase je mehr darf. Die Schwellen sind
    # Erstkalibrierungen; Kell selbst nennt keine Zahlen.
    "kell_zyklus": {
        "exhaustion_abstand": 0.15,  # 15 % ueber der 10er-Linie = Ueberdehnung
        "reversal_abstand": 0.15,    # 15 % darunter = Kapitulation
        "pop_fenster": 10,           # Rueckblick fuer die Rueckeroberung
        "pop_mindesttage": 3,        # so viele Tage lag der Kurs unter BEIDEN Linien
        # 4 statt 6 Prozent: Der eigene Selbsttest zeigte, dass 6 %
        # auch einen stetigen Trend von 0,7 % je Tag als Basis
        # durchwinkt — eine Basis, die niemand als solche erkennt.
        "basen_spanne": 0.04,        # 8-Tage-Spanne unter 4 % = Base n' Break
    },

    # --- Volumen (gilt EINHEITLICH für Scanner UND Wächter!) ---
    # GERECHNET WIRD AUSSCHLIESSLICH IN volumen.py — IBD "Volume % Change"
    # mit Hochrechnung über die Fünf-Minuten-Referenzkurve. Hier stehen nur
    # noch die Schwellen.
    "volumen": {
        # 50 STATT 10 TAGE (Gerhard, 28.07.2026 nachmittags). IBD-Standard.
        # ACHTUNG für die Akten: Das widerruft seine eigene Festlegung vom
        # Vormittag desselben Tages ("einheitlich 10 Tage für Scanner UND
        # Wächter"). Er hat den Wechsel im Übergabepapier ausdrücklich als
        # eigene, bewusste Entscheidung neben der Formelkorrektur benannt.
        "fenster_tage": 50,          # Durchschnittsvolumen über N Handelstage
        "breakout_faktor": 1.0,      # Standard: Volumen > Ø
        "breakout_faktor_vcp": 1.4,  # VCP strenger: ≥ 140 % vom Ø
        # VON 5× AUF 3× GESENKT (Gerhard, 05.08.2026). Seine Begründung
        # nach dem Nachrecherchieren: KEINE der etablierten Quellen
        # verlangt das Fünffache. Weinstein nennt für einen gültigen
        # Stage-2-Ausbruch das Zwei- bis Dreifache, IBD bei vergleichbaren
        # Mustern 40 bis 50 % über dem Durchschnitt. Die 5× waren damit
        # strenger als jeder publizierte Standard — und die Messung vom
        # 04.08. (das Kriterium verschlechtert das Ergebnis) passt dazu.
        # Genommen wird das obere, strengere Ende von Weinsteins Spanne.
        "gap_and_go_faktor": 3.0,    # Lücken-Bestätigungstag: ≥ 3× Ø
        # WER DARF OHNE VOLUMENBESTAETIGUNG MELDEN? (Gerhard, 12.08.2026)
        # Nur noch diese drei. Bei allen uebrigen Mustern wird ein
        # Ausbruch ohne Volumenbestaetigung gar nicht mehr gemeldet — er
        # bleibt offen und kommt erst, wenn das Volumen nachzieht (das
        # macht der Nachtrag, den es seit 29.07.2026 gibt).
        #
        # Die drei sind nicht willkuerlich: Bei ihnen IST das Volumen
        # Teil des Musters und wird eigens geprueft, statt nur als Filter
        # obendrauf zu liegen. Gap and Go verlangt das Dreifache am
        # Luecken-Tag, beide Red-to-Green-Kapitel eine dreiteilige
        # Signatur (ruhiger Anflug, Sprung, haelt an), die Flagge das
        # Volumen im Fahnenmast.
        #
        # ACHTUNG, was das NICHT betrifft: den dritten Status "nicht
        # verifizierbar". Der heisst "konnte gar nicht geprueft werden"
        # und ist etwas anderes als "geprueft und zu schwach" — genau
        # darauf hat Gerhard am 06.08.2026 bestanden. Er wird weiterhin
        # gemeldet, sonst verschwaende eine Aktie ohne eigene
        # Volumenkurve lautlos.
        "unbestaetigt_melden_bei": [
            "Red-to-Green",
            "Red-to-Green Explosive",
            "High & Tight Flag",
            # Der Innen-Einstieg ist dieselbe Flagge mit engerer Marke
            # (Soreide-Ausbau, 31.08.2026, Regelfrage G9): Das Volumen
            # steckt wie bei der Flagge im Fahnenmast, also gilt
            # dieselbe Ausnahme.
            "HTF Innen-Einstieg",
            "Lücken-Bestätigungstag",
        ],
    },

    # --- Insider-Kauf-Scanner (Gerhards Kapitel vom 14.08.2026) -----------
    # SEC Form 4, Transaktionscode "P" (echter Kauf am freien Markt).
    # Zwei unabhaengige Pfade, jeder fuer sich ausreichend:
    #   A  Groesse:  EIN Kauf >= min(5 % der Marktkap, 25 Mio $)
    #   B  Cluster:  >= 3 verschiedene Insider, je >= 2 % der Marktkap,
    #                innerhalb von 10 HANDELSTAGEN
    # ALLE Werte sind Gerhards begruendete Startwerte, KEINE gemessenen
    # Optima - sein eigener Hinweis. Sie gehoeren mitgeschrieben und
    # nachgeschaerft, bevor jemand darauf Geld setzt.
    "insider": {
        "min_marktkap": 300_000_000,        # kleinere Firmen sind Rauschen
        "pfad_a_prozent_marktkap": 0.05,
        "pfad_a_dollar_min": 25_000_000,    # was NIEDRIGER ist, gilt
        "pfad_b_prozent_pro_person": 0.02,
        "pfad_b_min_insider": 3,
        "cluster_fenster_tage": 10,         # Handelstage, nicht Kalendertage
        "melden": True,                     # meldet der Waechter die Funde?

        # WIE VIELE TAGE JE LAUF (Befund 26.08.2026): Der Scanner fragte
        # bis dahin NUR den heutigen Tagesindex ab - den es bei der SEC
        # noch gar nicht gibt (sie antwortet darauf mit 403). Ergebnis:
        # Seit dem ersten Cloud-Lauf am 14.08. null Funde, zwoelf Tage
        # lang, ohne dass irgendetwas nach Fehler aussah. Jetzt werden
        # die letzten Handelstage abgearbeitet; die Zugangsnummern-
        # Dedup sorgt dafuer, dass jede Einreichung trotzdem nur einmal
        # gelesen wird.
        #
        # 0 heisst: aus dem Cluster-Fenster errechnen (siehe
        # insider_edgar.index_rueckblick). GERHARDS REGEL VERLANGT DAS:
        # Pfad B sucht drei Insider innerhalb von cluster_fenster_tage
        # HANDELSTAGEN. Wer nur die letzten fuenf Indizes liest, hat die
        # erste Haelfte dieses Fensters nie gesehen - ein Cluster, das
        # am 12. beginnt und am 25. drei Kaeufer zaehlt, faellt dann
        # durch. Im Dauerbetrieb faellt das nicht auf (der Speicher
        # waechst mit), nach jedem Ausfall und jedem Neuaufbau sehr
        # wohl. Ein eigener Wert ueberstimmt die Rechnung.
        "index_tage_zurueck": 0,

        # LIVE-STROM (26.08.2026, Mathias' Frage nach tagesaktuellen
        # Kaeufen): EDGAR fuehrt neben dem Tagesindex einen Strom der
        # gerade eingegangenen Einreichungen. Der Tagesindex des
        # laufenden Tages entsteht erst nach Handelsschluss - der Strom
        # liefert schon vorher. GEMESSEN am 26.08.2026: Die heute
        # eingereichten Form 4 enthielten Kaeufe von GESTERN (die
        # gesetzliche Frist betraegt zwei Werktage), der Tagesindex
        # haette sie erst morgen gezeigt. Ein Tag Vorsprung.
        # Je Seite 100 Einreichungen; fuenf Seiten reichen rund einen
        # Tag zurueck (gemessen: 500 Eintraege bis zum Vortag-Nachmittag).
        "live_feed_seiten": 5,
    },

    # --- Sektor-Radar (Gerhards Paket vom 13.08.2026) ---------------------
    # Dreht gerade eine ganze Branche? Zwei bereits etablierte Regeln,
    # keine neue Kennzahl: Kreuzung des eigenen 10-Tage-Schnitts UND ein
    # Ausschlag in unserer Volumenformel am selben Tag.
    #
    # NICHT hier steht "bestaetigung_tage": Gerhards Entwurf fuehrt den
    # Wert, sein Code liest ihn nie. Ein Einstellwert, den niemand liest,
    # ist schlimmer als keiner - wer ihn verstellt, aendert nichts und
    # glaubt es doch. Die Spanne der Bestaetigung ist deshalb in
    # sektor_radar.BESTAETIGUNG_ABSTAND benannt und fest.
    "sektor_radar": {
        "ma_tage": 10,               # Umkehr gegen den eigenen 10-Tage-Schnitt
        "vol_pct_schwelle": 50.0,    # Volume % Change mindestens +50 %
        "v50_tage": 50,              # Durchschnittsbasis, IBD-Standard
        "melden": True,              # meldet der Waechter zur Eroeffnung?
    },

    # --- Gleitende Durchschnitte ---
    "ma": {
        "kurz": 21,                  # Trend Template: Steigung der MA200 ueber 21 Tage
    },

    # --- 52-Wochen / Lookbacks ---
    "lookback": {
        "jahr_tage": 252,            # 52 Wochen
        "rs_quartale": [63, 126, 189, 252],   # RS-Rating-Fenster
        "rs_gewichte": [0.40, 0.20, 0.20, 0.20],
        # Kappung jeder Einzelrendite nach oben (Gerhard, 12.09.2026 abends,
        # dritte Antwort auf den IBD-Abgleich): plus 50 Prozent je Zeitraum,
        # damit ein Vervielfacher aus dem Vorjahr nicht alles ueberstrahlt.
        # GEMESSEN 12.09.2026: dreizehn oeffentliche IBD-Werte innerhalb von
        # 5 Punkten getroffen; 0,45 bis 0,55 gleich gut, ab 0,7 bricht es ein.
        "rs_kappung": 0.50,
    },

    # --- Strategie-Schwellen ---
    "gap_and_go": {
        "gap_min": 0.07,             # ≥ 7 %
        "schluss_position_min": 0.80,
        # W2 (Gerhard, 12.09.2026): Der Folgetags-Einstieg nach einem
        # Luecken-Bestaetigungstag gilt nur bis 3 Prozent ueber dem
        # Kaufpunkt, enger als das allgemeine Einstiegsfenster von 5.
        "einstieg_grenze": 0.03,# oberes Fünftel
        # WELCHE FLAT BASE GILT (Mathias, 03.08.2026): "original" oder "A".
        # Umschalten heißt: diese eine Zeile ändern, sonst nichts.
        #
        # Der Grund für "original": Nachgemessen über acht Monate, alle
        # 265 Aktien, rund 28.400 Aktien-Tage — Gap and Go hätte mit
        # Fassung A KEIN EINZIGES Mal ausgelöst, mit keinem der drei
        # Volumen-Maßstäbe. Und das Volumen war dabei nicht der Engpass:
        # Von 108 verteidigten Lücken erfüllten 13 das Fünffache gegen
        # Ø10 und 20 gegen Ø50, aber nur EINE hatte zugleich eine Flat
        # Base nach Fassung A. Fassung A siebt 108 auf 10 herunter und
        # trifft dabei genau die Katalysator-Lücken; übrig bleiben ruhige
        # Lücken mit 1,3- bis 2,6-fachem Volumen, also die Fälle, die das
        # Volumenkriterium aussortieren soll. Die Kriterien arbeiten
        # gegeneinander. Das Original hätte 30 statt 10 durchgelassen.
        #
        # GILT BIS GERHARD ETWAS ANDERES ENTSCHEIDET. Fassung A war seine
        # verbindliche Vorgabe vom 28.07.2026 und steht unverändert
        # daneben — sie ist nicht gelöscht, nur nicht in Kraft.
        "flat_base_fassung": "original",
        "flat_base": {
            # Der ältere Entwurf aus Kapitel 7: langes Fenster, weite
            # Spanne, keine Bedingung an gleitende Durchschnitte. Genau
            # diese Werte wurden im Rückblick gegengeprüft.
            "original": {"tage": 63, "max_spanne": 0.35, "ma": []},
            # Gerhards Fassung A vom 28.07.2026, die spätere O'Neil/IBD-
            # Fassung: mindestens 5 Wochen, höchstens 15 % Spanne, und
            # der Kurs muss über MA10 und MA21 liegen.
            "A": {"tage": 25, "max_spanne": 0.15, "ma": [10, 21]},
        },
    },
    # --- Kapitel 9: Red-to-Green am Markt-Gap-Tag -------------------------
    # Gerhards Präzisierung vom 02.08.2026 ersetzt die bisherige vage Regel
    # "Volumen zieht an" durch eine exakte Signatur in zwei Phasen. Beide
    # rechnen über dieselbe F(t)-Tagesverlaufskurve wie der Rest des Systems
    # (volumen.py) — es gibt nur EINE Volumen-Wahrheit.
    "red_to_green": {
        "nasdaq_gap_scharf": -0.015, # Nasdaq ≥ 1,5 % im Minus
        "aktie_gap_min": -0.05,      # Aktie ≥ 5 % runter
        "rs_min": 90,                # RS Rating > 90
        "min_ueber_tief": 0.50,      # ≥ 50 % über 52-Wochen-Tief
        "ema_kurz": 21,              # Kurs muss über EMA21 …
        "ema_lang": 50,              # … und über EMA50 stehen
        # ANFLUG: Vor der Kreuzung darf das Volumen höchstens im
        # Normaltempo laufen. 0 % Abweichung heißt genau 100 % des
        # 50-Tage-Schnitts, hochgerechnet auf die Uhrzeit.
        "vol_anflug_max_pct": 0.0,
        # SPRUNG: An der Kreuzung muss es auf mindestens doppeltes
        # Normaltempo springen.
        "vol_sprung_min_pct": 100.0,
        # Kreuzt es in den ersten 30 Minuten, entfällt die Anflug-
        # Bedingung: Die Eröffnungsphase ist ohnehin volumenstark, und das
        # steckt bereits in der F(t)-Kurve.
        "fruehe_phase_minuten": 30,
        # Der Sprung muss halten: in den folgenden 10 Minuten höchstens
        # 20 % Abfall, sonst war es eine Eintagsfliege.
        "sprung_bestaetigung_minuten": 10,
        "sprung_abfall_max": 0.20,
        # Gerhard, 02.08.2026, wörtlich: Beide Werte sind Startwerte, kein
        # gemessenes Optimum — erst mitschreiben, dann nachjustieren.
    },
    # --- Exit-Regelwerk (Gerhard, 05.08.2026, systemweit) -----------------
    # DAS GRUNDPRINZIP, und es dreht die bisherige Denkweise um: Der Stop
    # kommt NICHT aus einem Risikobudget. Er steht aus dem CHART fest, an
    # dem Punkt, wo das Muster strukturell gebrochen ist — dort also, wo
    # die These widerlegt ist, die den Einstieg begründet hat.
    #
    #     stop = max(struktureller Bruchpunkt, Einstieg × 0,90)
    #
    # Die zehn Prozent sind eine Obergrenze und nie das Ziel. Sie greifen
    # nur, wenn der Strukturpunkt weiter weg liegt oder das Muster gar
    # keinen liefert. Geprüft wird IMMER auf Schlusskursbasis — ein Docht
    # darunter löst nicht aus, sonst wirft normales Tagesrauschen saubere
    # Positionen hinaus.
    #
    # Quellen der Zahlen: Minervini (Stop 6 bis 8 %, nie über 10 %; Trail
    # über MA21 und MA50), O'Neil und IBD (20 bis 25 % Gewinnmitnahme,
    # 8-Wochen-Halteregel, Round-Trip-Verbot), Bulkowski (Unterstützungs-
    # zone schlägt den rechnerischen Stop), Darvas (Boxboden und
    # Box-Stacking). Alles Ausgangswerte für die Messung, keine
    # gemessenen Optima.
    "exit": {
        "stop_deckel_pct": 0.10,      # absolute Obergrenze, nie das Ziel
        "breakeven_ab_r": 2.0,        # Stufe A: ab 2R Stop auf Einstand
        "breakeven_ab_pct": 0.10,     # Stufe A alternativ: ab 10 %
        "teilverkauf_ab_pct": 0.20,   # Stufe B: Teilverkauf ab 20 %
        "teilverkauf_anteil": 0.50,   # Stufe B: die Hälfte
        # Ebene 3, die wichtigste Einzelregel: 20 % in unter drei Wochen
        # heben den Teilverkauf auf, dann wird acht Wochen gehalten.
        "schnellstarter_pct": 0.20,
        "schnellstarter_tage": 15,    # drei Wochen in Handelstagen
        "halteregel_tage": 40,        # acht Wochen ab Ausbruch
        "trail_ma_schnell": 21,       # Stufe C, zügige Bewegungen
        "trail_ma_langsam": 50,       # Stufe C, ruhige Bewegungen
    },
    # --- Kapitel 12: Meldungen der Gewinnseite ----------------------------
    # STRAFFUNGS-MELDUNGEN ABGESCHALTET (Gerhards Wunsch über Mathias,
    # 10. und 11.09.2026, bis auf Weiteres). Betroffen sind genau drei
    # Befunde, deren Meldung zu einer Straffung rät:
    #   Musterziel erreicht  "Teilverkauf oder harte Straffung"
    #   Wedge Drop           "Ausstieg oder harte Straffung"
    #   Sektor dreht         "Straffung erwägen"
    # Der Nachtlauf legt sie gar nicht erst ab, und der Wächter meldet sie
    # auch aus einer älteren Ablage nicht. Die Zone rechnet weiter mit dem
    # erreichten Musterziel, sie ist keine Meldung. NICHT betroffen:
    # Kapitel 11 samt "Nachzieh-Linie unterschritten, Rest raus"
    # (positionen.py), Zonenwechsel, Klimax-Zeichen, Weinstein Stufe 3,
    # Zeitdeckel und Zahlen-Hinweis. Wieder einschalten heißt True setzen;
    # gemeldet wird dann nur, was mit den Kursen dieses Tages noch gilt.
    "gewinnseite": {
        "straffungs_meldungen": False,
    },
    # --- Cup & Handle auf Wochenbasis ("Giant Base") ----------------------
    # Gerhards Ergänzung vom 04.08.2026. Sie ERSETZT die bestehende
    # Tages-Erkennung NICHT, sondern läuft daneben.
    #
    # Der Fehler, den sie behebt: Bei sehr langen Konsolidierungen sieht
    # die Tagesfunktion den echten linken Rand nicht mehr — ihr Fenster
    # von rund 160 Tagen ist dafür zu kurz. Übrig bleibt ein Ausschnitt,
    # der dann als Rectangle Top gemeldet wird. Aufgefallen an DDOG: Die
    # Aktie brach am 01.08. über einen von IBD bestätigten
    # Cup-&-Handle-Kaufpunkt aus, unser System meldete Rectangle Top zum
    # gleichen Kurs.
    #
    # WARUM BEIDE NEBENEINANDER LAUFEN, wörtlich von Gerhard: Die
    # gelockerten Toleranzen hier sind auf sehr lange Formationen
    # kalibriert. Auf kurze Cups angewandt würden sie Fehlsignale
    # durchlassen, die die strengere Tagesfunktion zu Recht aussiebt.
    "cup_handle_v2": {
        "cup_min_len_wochen": 5,      # wie IBDs Flat-Base-Mindestlänge
        "cup_max_len_wochen": 104,    # bis zwei Jahre, deckt Giant Bases ab
        "cup_min_depth": 0.12,
        "cup_max_depth": 0.60,
        # Randtoleranz 11 % statt 6 %: Bei sehr tiefen, langen Cups muss
        # der rechte Rand das alte Hoch nicht so eng zurücktesten. Der
        # echte MEDP-Fall brauchte 9,3 %.
        "cup_rim_tolerance": 0.11,
        "handle_min_len_wochen": 1,
        # HANDLE-FENSTER PROPORTIONAL ZUR CUP-LÄNGE (Gerhard, 05.08.2026,
        # nach meinem Einwand): Cup-Länge geteilt durch drei, begrenzt auf
        # mindestens 8 und höchstens 16 Wochen.
        #
        # Untergrenze 8, damit kurze Cups nicht plötzlich strenger werden
        # als bisher. Obergrenze 16, weil ein sehr langer Handle laut
        # O'Neil selbst ein Warnzeichen ist und kein Qualitätsmerkmal.
        #
        # Anlass: DDOG, also der Fall, der den ganzen Fix ausgelöst hat,
        # wurde mit festen 8 Wochen NICHT erkannt — sein Handle lief
        # länger. Eine feste 16 wäre Kurvenanpassung an einen Einzelfall
        # gewesen, die proportionale Grenze folgt derselben Logik wie
        # Gerhards Lockerung der Handle-POSITION ("zu strikt für
        # proportional große Formationen").
        "handle_max_len_wochen": 8,        # nur noch als Untergrenze
        "handle_teiler": 3,                # Cup-Länge geteilt durch …
        "handle_max_len_obergrenze": 16,
        # Rücksetzer höchstens 45 % der Cup-Höhe (Standard-Cup: 33 %).
        # Das bleibt die eigentliche Qualitätsprüfung.
        "handle_max_retrace": 0.45,
        # Handle in der oberen HÄLFTE statt im oberen Drittel. Die
        # Positionsregel war für proportional große Formationen zu streng.
        "handle_min_position": 0.50,
        "outlier_glaettung_fenster": 3,   # Median gegen Einzelausreißer
        "min_score": 50,
        "symmetrie_min": 0.15,        # Boden darf unsymmetrisch liegen
        "symmetrie_max": 0.85,
        "r2_min": 0.50,               # gelockert, weil vorher geglättet
    },
    # --- Kapitel 10: Shakeout-Spring (Wyckoff) ----------------------------
    # Werte aus Gerhards shakeout_engine.py, Fassung v2 vom 02.08.2026.
    "shakeout": {
        "ma_lang": 200,
        "stage2_min_tage_steigend": 21,   # MA200 seit rund einem Monat steigend
        "min_ueber_52w_tief": 1.00,       # ≥ 100 % über dem 52-Wochen-Tief
        # Ein "lookback_tage" von 1000 stand bis 13.09.2026 hier; gelesen
        # hat ihn niemand. Der Level-Detektor sieht die Historie, die der
        # Nachtscan laedt (zwei Jahre, period="2y").
        "swing_order": 5,                 # Fenster für Swing-Punkte (Tage)
        "swing_order_wochen": 2,          # dasselbe auf Wochenbasis
        "cluster_toleranz": 0.02,         # 2 % — Punkte zu einer Zone gruppieren
        "shakeout_toleranz": 0.05,        # höchstens 5 % unter die Zone
        # AM 02.08.2026 VON 0,90 AUF 0,70 GELOCKERT (Gerhard): oberes
        # Drittel der Tagesspanne statt oberste 10 Prozent. Begründung aus
        # dem Backtest: mehr echte Signale bei weiterhin klarem Schluss.
        "schluss_oberste_pct": 0.70,
        "level_score_schwelle": 55,
        "ma_naehe_toleranz": 0.03,
        # Gewichte der fünf Faktoren; sie müssen sich nicht auf 100 summieren.
        "gewicht_beruehrungen": 30,
        "gewicht_volumen": 30,
        "gewicht_alter_extrempunkt": 15,
        "gewicht_wochenchart": 15,
        "gewicht_ma_naehe": 10,
        # Wyckoff-Volumentyp am Spring-Tag, gemessen am Ø der letzten 20 Tage.
        "vol_typ1_max": 0.7,              # unter 70 % = Typ 1, beste Qualität
        "vol_typ3_min": 1.5,              # über 150 % = Typ 3, Test abwarten
        "vol_typ_fenster": 20,
        # Sekundärtest: Der bestätigende Rücksetzer darf bis zu 15
        # Handelstage auf sich warten lassen.
        "sekundaertest_max_wartetage": 15,
        "sekundaertest_max_zusatz_unterschreitung": 0.02,
        "kursziel_faktor": 1.0,           # Zonenhöhe einmal auf die Oberkante
    },
    "crash_support": {
        "min_marktkap_mrd": 20,
        "min_umsatzwachstum": 0.15,
        "max_debt_to_equity": 0.5,
        "level_score_schwelle": 60,
        "regime_index_drawdown": -0.10,  # SPY ≥ 10 % unter Hoch
        # ABGELEITET, nicht von Gerhard: Er nennt keinen Auslöser.
        # "zone_schluss"    Schlusskurs IN der Zone — die Unterstützung
        #                   hat auf Schlusskursbasis gehalten (Vorgabe).
        # "rueckeroberung"  Zone unterschritten, Schluss wieder darüber.
        "trigger": "zone_schluss",
        "kursziel_faktor": 1.0,          # Zonenhöhe einmal auf die Oberkante
    },
    # --- Kapitel 11: Red-to-Green EXPLOSIVE (Mathias, 12.08.2026) ---
    # Anlass war Fastly am 10.08.2026: Die Aktie eroeffnete bei 22,45 und
    # damit 2,2 % UNTER dem Vortagesschluss, drehte und schloss bei 27,75,
    # also 20,9 % im Plus. Von der Eroeffnung bis zum Schluss waren es
    # 23,6 %. Gemeldet wurde nichts, und zwar aus zwei Gruenden:
    #
    #   * Eine BASIS gab es nicht — die zwoelf Tage davor hatten eine
    #     Spanne von 43,8 %. Also kein Darvas, kein Rectangle, kein Cup.
    #   * Eine LUECKE gab es auch nicht — Gap and Go verlangt sieben
    #     Prozent nach OBEN, hier waren es 2,2 nach unten.
    #   * Und Kapitel 9 verlangt ZWEI Dinge, die beide fehlten: der Nasdaq
    #     haette mindestens 1,5 % nach unten aufmachen muessen (er
    #     eroeffnete mit -0,04 %), und die Aktie selbst mindestens 5 %
    #     (es waren 2,2).
    #
    # Kapitel 9 ist eine PANIK-Regel: ganzer Markt bricht ein, starke
    # Aktie faellt mit, dreht als Erste. Kapitel 11 ist etwas anderes —
    # die Aktie dreht AUS EIGENEM ANTRIEB, ohne dass der Markt etwas
    # damit zu tun haette. Deshalb ein eigenes Kapitel und keine
    # Aufweichung von Kapitel 9: Gerhard hat dessen Bedingungen mit
    # Bedacht so eng gefasst, und sie bleiben unangetastet.
    #
    # ES GIBT HIER BEWUSST KEINEN NASDAQ-SCHALTER (Mathias' Vorgabe vom
    # 12.08.2026). Die Marktlage spielt keine Rolle; gesucht wird die
    # Aktie, die aus sich heraus dreht.
    "red_to_green_explosive": {
        # Der einzige gelockerte Wert: zwei statt fuenf Prozent. Genug,
        # um einen roten Start zu verlangen, wenig genug, um Faelle wie
        # Fastly (-2,2 %) zu erwischen.
        "aktie_gap_min": -0.02,
        # ALLES UEBRIGE ist wortgleich Kapitel 9 (Mathias: "ansonsten
        # genau so"). Die Werte stehen hier ausgeschrieben statt geerbt,
        # damit man beide Kapitel nebeneinander lesen kann und niemand
        # eines aendert und dabei das andere mitverstellt.
        "rs_min": 90,
        "min_ueber_tief": 0.5,
        "ema_kurz": 21,
        "ema_lang": 50,
        "vol_anflug_max_pct": 0.0,
        "vol_sprung_min_pct": 100.0,
        "fruehe_phase_minuten": 30,
        "sprung_bestaetigung_minuten": 10,
        "sprung_abfall_max": 0.2,
    },

    "darvas": {
        "box_tage": 3,
        "frische_max_tage": 25,
    },

    # --- Betrieb ---
    "betrieb": {
        "zeitzone_boerse": "America/New_York",  # ALLES in Börsenzeit rechnen
        "stale_max_sekunden": 120,   # Rückfallwert für unbekannte Quellen
        # Veraltungs-Schwelle PRO QUELLE (Gerhard, 28.07.2026). Eine
        # einheitliche 2-Minuten-Grenze wäre falsch: Der WebSocket liefert
        # tickweise — dort heißt zwei Minuten Stille wirklich "Leitung
        # hängt". yfinance liefert verzögert und wird nur alle sechs
        # Minuten abgefragt; mit 2 Minuten wäre dort STÄNDIG alles stale.
        "stale_pro_quelle": {
            # Yahoos Live-Strom. NICHT so streng wie beim früheren
            # Finnhub-Strom (2 Minuten): Gemessen am 28.07.2026 lag der
            # letzte Kurs im Mittel 36 Sekunden zurück, drei Viertel unter
            # 102 Sekunden — aber der schlechteste Wert bei 22 Minuten,
            # schlicht weil manche Aktien so selten gehandelt werden. Mit
            # 2 Minuten würde genau dieser Bodensatz ständig als "hängend"
            # verworfen, obwohl der Kurs stimmt. 15 Minuten trennen
            # sauber: Eine echte Störung fällt auf, eine ruhige Aktie nicht.
            "yahoo_ws": 900,
            "finnhub_ws": 120,       # tickweise: 2 Min Stille = Leitung hängt
            "finnhub": 300,
            "twelvedata": 600,
            "yfinance": 1200,        # verzögert, Minutentakt: 20 Minuten
        },
        # Takt des schweren Tagesdaten-Abrufs. Begründung ausführlich in
        # breakout_watcher.py bei TAKT — kurz: nachgemessen, ein Abruf
        # dauert 5 bis 7 Sekunden, zehn hintereinander liefen sauber, und
        # seit Kurs und Volumen live kommen, muss dieser Abruf gar nicht
        # mehr schnell sein.
        "takt_sekunden": 60,
        # Prüftakt: So oft wird auf gerissene Kaufpunkte geprüft. Getrennt
        # vom Datentakt (Mathias, 28.07.2026: "Stelle auf Echtzeit um").
        # Kurs, Tagesvolumen und Tagesspanne kommen laufend aus dem Strom,
        # die Prüfung muss also nicht auf den schweren Abruf warten.
        # Bewusst 2 Sekunden und nicht "bei jeder Kursmeldung": Der Strom
        # schickt rund 3600 Meldungen je Minute — das wären 3600 volle
        # Durchläufe für einen Gewinn von Sekundenbruchteilen. Gegenüber
        # den ursprünglichen sechs Minuten ist das der Faktor 180.
        # FESTER TAKT von 2 Sekunden (Mathias, 30.07.2026 bestätigt):
        # Die Schleife schläft die vollen zwei Sekunden und rechnet dann
        # alles durch. Am 30.07. war das kurzzeitig anders — erst weckte
        # jede Kursmeldung die Prüfung, dann standen 20 Sekunden drin;
        # beides ist zurückgenommen.
        #
        # Die Last bei Yahoo hängt NICHT daran: Der Strom ist eine
        # stehende Verbindung, die von sich aus sendet, und der schwere
        # Tagesdatenabruf läuft unabhängig davon im takt_sekunden.
        # Zwischen 2 und 20 Sekunden liegt dort kein einziger Zugriff
        # Unterschied.
        "pruef_takt_sekunden": 2,
        # WIE WEIT UEBER DEM KAUFPUNKT gilt ein Ausbruch noch als sauber
        # einsteigbar? Darueber wird nicht mehr als Kaufsignal gemeldet.
        # Die Zahl stand bis 11.08.2026 fest im Waechter.
        "nachlauf_grenze": 0.05,
        # Und was passiert MIT dem, was darueber liegt? Seit 11.08.2026
        # (Gerhards Fall Sea, das den Kaufpunkt mit einer Eroeffnungsluecke
        # von 10,3 % uebersprang) gibt es dafuer eine EIGENE Meldung:
        # "Kaufpunkt uebersprungen". Sie ist ausdruecklich KEIN Kaufsignal,
        # sondern die Auskunft, dass etwas passiert ist. Auf False setzen,
        # wenn nur noch handelbare Ausbrueche gemeldet werden sollen.
        "melde_uebersprungene": True,
        # ZWISCHENLOESUNG ZU FRAGE M4 (Mathias, 11.09.2026): Ein Ausbruch
        # wird nur noch gemeldet, wenn er HEUTE passiert ist - lag der
        # Schlusskurs des Vortags schon ueber dem Kaufpunkt, war der Riss
        # gestern, und die Meldung waere ein Vortagesalarm in neuem Kleid.
        # GEMESSEN am Trigger-Logbuch 09. bis 11.09.2026: 12 von 57
        # Ausbruechen lagen schon mit dem Vortagesschluss ueber dem
        # Kaufpunkt, und jeder davon wurde in den ersten Minuten nach der
        # Eroeffnung gemeldet (MATX, ALSN und OOMA am 11.09.; FCFS, PBF,
        # FIVE und PTGX am 10.09.; ASH, KEYS, OSCR, LITE und CXW am 09.09.).
        # Fehlt der Vortagesschluss, wird wie bisher gemeldet - nur ein
        # BEKANNTER Vortagesschluss ueber dem Kaufpunkt schweigt.
        # GERHARD HAT ENTSCHIEDEN (M4, 12.09.2026): Moeglichkeit 2. Der
        # Fensterzustand bleibt ueber Nacht erhalten, ein Wiedereintritt
        # laeuft nur ueber die Totzone; ein Vortagesschluss ueber dem
        # Kaufpunkt schweigt damit von selbst, ohne diese Zwischenloesung.
        # Und W1: Die "Bestaetigung am Folgetag" wird innerhalb des
        # Einstiegsfensters (bis 5 Prozent) gemeldet, nicht unterdrueckt.
        "nur_frische_ausbrueche": False,
        # WIEDEREINTRITT (Mathias, 13.08.2026): Faellt der Kurs wieder ins
        # Einstiegsfenster zurueck, wird das gemeldet - "das Fenster ist
        # das Fenster". Damit ein Kurs, der genau auf der Grenze liegt,
        # nicht staendig hin und her meldet, geht es erst UNTER
        # (nachlauf_grenze minus totzone) wieder hinein.
        # GEMESSEN an MNDY-Minutendaten vom 13.08.2026: ohne Totzone
        # NEUN Meldungen in 22 Minuten (sechs Ueberquerungen), mit einem
        # Prozentpunkt Totzone genau EINE. Auf 0 gesetzt gibt es die
        # Reinform, in der jede Ueberquerung zaehlt.
        #
        # ZWEI Prozentpunkte auf GERHARDS Entscheidung (13.08.2026,
        # Mathias hat mit ihm geredet): Wieder herein geht es erst bei
        # 3 % ueber dem Kaufpunkt, nicht schon bei 4. Der Kurs muss also
        # wirklich in die Kaufzone zurueckkommen und nicht bloss an ihrem
        # Rand kratzen.
        "wiedereintritt_totzone": 0.02,
        # Weckuhr und Sammelfenster gab es nur am 30.07.2026 für ein paar
        # Stunden; mit dem festen Zwei-Sekunden-Takt sind sie wieder
        # heraus. Ebenso die Obergrenze von fünf Aktien je Push: Sie
        # zerschnitt Meldungen, die zusammengehören (Mathias: "sonst
        # kommen 2 Nachrichten auf ein Mal, die eig. eine sind").
        # Geteilt wird ausschließlich nach der Zeichenzahl, siehe
        # NTFY_GRENZE in breakout_watcher.py.
        "min_historie_tage": 60,     # weniger Historie → Aktie überspringen
        # KEIN Einstellwert fuer Actions-Minuten: heliot ist oeffentlich, dort
        # sind sie unbegrenzt (nachgeprueft 27.07.2026). Die Grenze, die
        # wirklich beisst, sind sechs Stunden je Auftrag, deshalb die
        # Zweiteilung der Wache (GITHUB_GRENZE_MIN in breakout_watcher.py).
        # M1 (Gerhard, 12.09.2026), Variante A: Die Schlusskurs-Befunde
        # (Zeitdeckel, Klimax, Zonen, 8-EMA-Hinweis, Sektor-Radar) werden
        # gegen 15:45 New York mit den Handelskursen gerechnet und VOR
        # 16:00 gemeldet, mit dem Hinweis "Schluss noch offen". Minute des
        # Handelstags, ab der das geschieht (945 = 15:45).
        "schlussnahe_minute": 945,
    },

    # --- Relative Staerke gegen den ganzen US-Markt (R1 bis R6, Teil 6) ---
    # Gerhards Antworten vom 12.09.2026, am selben Abend ergaenzt um drei
    # Antworten auf den IBD-Abgleich (ueber Mathias): Vergleichsbasis ist
    # der GANZE US-Markt, die Schwellen sind nur noch Kennzeichnung, jede
    # Einzelrendite wird gekappt (lookback.rs_kappung). Reine Anzeige, kein
    # Filter (die einzige Ausnahme bleibt die Fokusliste in red_to_green,
    # RS ueber 90).
    "rs_universum": {
        # R1: alle Stammaktien aus den amtlichen Symbolverzeichnissen der
        # Nasdaq (nasdaqlisted.txt) und der uebrigen Boersen (otherlisted.txt;
        # N = NYSE, A = NYSE American; Arca, BATS und IEX fuehren praktisch
        # nur ETFs und bleiben draussen).
        "quelle": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "quelle_andere": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
        "andere_boersen": {"N": "NYSE", "A": "NYSE American"},
        # R2: Mindestkurs 15 Dollar, Tagesumsatz 10 Millionen Dollar im
        # 50-Tage-Schnitt; ETFs und Fonds draussen, SPACs erst nach der
        # Uebernahme. Seit 12.09.2026 abends NUR KENNZEICHNUNG ("im
        # Universum"): Die Vergleichsbasis fuer das Perzentil sind ALLE
        # Stammaktien mit voller Historie, auch die unter den Schwellen.
        "mindestkurs": 15.0,
        "mindest_dollarvolumen": 10_000_000.0,
        "dollarvolumen_tage": 50,
        # Luecke 6: unter 252 Handelstagen Historie "nicht verfuegbar".
        "historie_tage": 252,
        # Teil 6, Regel 1: Liefert der Abruf weniger als 95 Prozent des
        # Universums, gibt es KEIN RS, sondern "nicht verfuegbar".
        "mindest_abdeckung": 0.95,
        # R6: Zusatz "sehr gut" ab 85.
        "sehr_gut_ab": 85,
        # R5: RS-Linie gegen SPY und QQQ mit Hinweis auf ein neues Hoch.
        "indizes": ["SPY", "QQQ"],
        # R8: "Roter Markt" heisst nur der Nasdaq, und rot erst ab
        # mindestens 0,5 Prozent Minus.
        "markt_index": "^IXIC",
        "rot_ab_pct": 0.005,
        # Abruf ueber Yahoo in Bloecken. GEMESSEN 12.09.2026: 4.331
        # Nasdaq-Symbole in 300er-Bloecken, 14 Monate, 97 Sekunden, 4.328
        # mit Kursen (99,9 Prozent), keine Drosselung; 14 Monate decken
        # 252 Handelstage plus Reserve. NACHGEMESSEN 12.09.2026 abends: Ein
        # NYSE-Abruf in 300er-Bloecken verlor STILL 45 Prozent der Symbole
        # (1.103 gewoehnliche Titel wie IBM und MCD, ohne Fehlermeldung), in
        # 100er-Bloecken kam alles; dazu laedt kurse_holen still Fehlendes
        # einmal in 50er-Bloecken nach.
        "abruf_block": 100,
        "abruf_zeitraum": "14mo",
        # Wie viele Handelstage RS-Verlauf je Aktie mitgefuehrt werden
        # (fuer "Aenderung zur Vorwoche" in den Berichten).
        "rs_verlauf_tage": 30,
    },

    # --- Technische Kennzahlen je Aktie (Etappe 2, Entscheidungen 4 und 5) ---
    # Gerhard, 13.09.2026: alle 16 Kennzahlen der Gruppe A aus dem
    # Recherche-Papier (Teil 4.1), NUR ANZEIGE, keine davon filtert, auch ADR
    # nicht. Gerechnet in kennzahlen_technik.py, abgelegt je Aktie unter
    # "technik" in rs_universum.json.
    "technik": {
        # Punkt 1: ADR nach Qullamaggie, mittlere Tagesspanne (Hoch durch
        # Tief) ueber 20 Handelstage.
        "adr_tage": 20,
        # Punkt 9: Volatilitaet wie bei Finviz, dieselbe Rechnung ueber Woche
        # und Monat. GEMESSEN 14.09.2026 an AAPL, NVDA, MSFT, IBM und AAOI:
        # Finviz nimmt 5 und 21 Tage (mit 20 Tagen wich der Monat bei AAOI um
        # 0,8 Punkte ab).
        "volatilitaet_tage": [5, 21],
        # Punkt 2: ATR nach Wilder.
        "atr_tage": 14,
        # Punkt 3: Up/Down Volume Ratio nach IBD.
        "updown_tage": 50,
        # Punkt 4: A/D nach Chaikin, dasselbe Fenster wie die fruehere
        # Plus-Minus-Zaehlung (13 Wochen).
        "ad_tage": 65,
        # Punkte 5 und 12: Mansfield RS und Beta gegen diesen Index.
        "vergleich_index": "SPY",
        "mansfield_wochen": 52,
        # Punkte 5 und 6: "steigend" heisst hoeher als vor so vielen Wochen;
        # dieselbe Spanne misst die Steigung der 30-Wochen-Linie.
        "vergleich_wochen": 4,
        # Punkt 6: Weinstein-Stufe. Flach heisst, die Linie aendert sich in
        # vier Wochen um hoechstens 0,5 Prozent; ob davor ein Anstieg (Stufe
        # 3) oder ein Rueckgang (Stufe 1) lag, entscheidet das Quartal davor.
        "weinstein_linie_wochen": 30,
        "weinstein_flach_pct": 0.5,
        "weinstein_vorlauf_wochen": 13,
        # Punkt 7: Momentum Burst nach Stockbee und Episodic Pivot.
        "burst_pct": 4.0,
        "burst_mindestvolumen": 100_000,
        "pivot_luecke_pct": 10.0,
        # Volumenfaktor des Episodic Pivot: gegen den Schnitt so vieler Tage.
        "volumen_schnitt_tage": 50,
        # Punkt 8: Wertentwicklung wie bei Finviz. Zahlen sind Handelstage,
        # "jahr" heisst gegen den letzten Schluss am oder vor demselben
        # Kalendertag ein Jahr frueher. GEMESSEN 14.09.2026 an fuenf Aktien:
        # So stimmen alle 25 Bezugskurse mit Finviz, mit 252 Handelstagen fuer
        # das Jahr nur 20.
        "wertentwicklung_tage": {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "12m": "jahr"},
        # Punkt 10: Abstand zu den einfachen Durchschnitten und zum Hoch und
        # Tief dieses Fensters.
        "sma_tage": [20, 50, 200],
        "hoch_tief_tage": 50,
        # Punkt 12: Beta ueber so viele Tagesrenditen.
        "beta_tage": 252,
        # Punkt 13: RSI nach Wilder.
        "rsi_tage": [14, 2],
        # Punkt 14: Durchschnittsvolumen und Dollarvolumen.
        "volumen_tage": 63,
        "dollarvolumen_kurz_tage": 20,
        # Punkt 15: RS-Aenderung gegen den juengsten Verlaufseintrag, der so
        # viele Kalendertage zurueckliegt (eine und vier Wochen).
        "rs_aenderung_tage": {"1w": 5, "4w": 26},
        # Punkt 16: Die ganze Historie kommt als Monatskerzen von Yahoo, alle
        # so viele Tage fuer das ganze Universum; dazwischen wird das Hoch
        # jede Nacht fortgeschrieben. GEMESSEN 14.09.2026 an 100 Aktien: Das
        # hoechste Monatshoch ist bei allen 100 gleich dem hoechsten
        # Tageshoch, der Abruf braucht 2,5 statt 8,9 Sekunden je Block.
        "allzeithoch_abruf_tage": 7,
        # Weicht der gespeicherte Schlusskurs der Vornacht um mehr als diesen
        # Anteil von dem ab, den Yahoo heute fuer denselben Tag nennt, war es
        # ein Split, und das gespeicherte Allzeithoch wird umgerechnet.
        "allzeithoch_split_toleranz": 0.005,
        # Unbereinigter Split (Befund 14.09.2026, sechs Kleinwerte an einem
        # Tag): Springt der Schluss auf das Dreifache oder mehr (oder auf ein
        # Drittel), waehrend das Dollarvolumen hoechstens fuenffach
        # auseinanderliegt, hat die Kursquelle den Split noch nicht in die
        # Historie eingerechnet. Die Kennzahlen dieses Tages sind dann nicht
        # verfuegbar, statt falsch.
        "split_verdacht_faktor": 3.0,
        "split_verdacht_dollarvolumen": 5.0,
        # Zuerst gilt Yahoos eigene Split-Meldung, wenn sie an einem der
        # letzten so vielen Handelstage steht. GEMESSEN 14.09.2026: Yahoo
        # fuehrte fuer alle sechs Titel mit unbereinigtem Sprung einen Split
        # mit diesem Datum; die Dollarvolumen-Regel allein erkannte vier.
        "split_ereignis_tage": 5,
    },

    # --- Marktbreite und Marktphase (Etappe 3, Entscheidung 6) -------------
    # Gerhard, 13.09.2026: "JA BAUEN. Distribution Days, Follow-through Day,
    # Steiger und Faller, McClellan, Anteil ueber SMA 50 und 200, neue Hochs
    # und Tiefs, Stockbee-Zaehler. Die Ampel filtert weiterhin NICHTS."
    # Rechnung in marktbreite.py; die Indexwerte legt marktampel.py ab, die
    # Breite rs_universum.py unter "marktbreite". Alles nur Anzeige.
    "marktbreite": {
        # Distribution Day nach IBD (Papier 4.4 Punkt 6): Verlust ab so
        # vielen Prozent bei hoeherem Volumen als am Vortag; zaehlt so viele
        # Sitzungen, verfaellt frueher bei einem Tageshoch so viele Prozent
        # ueber dem Schluss dieses Tages.
        "dd_verlust_pct": 0.2,
        "dd_fenster": 25,
        "dd_verfall_pct": 5.0,
        # Stalling Day (ebenda): Gewinn unter so vielen Prozent bei hoeherem
        # Volumen als am Vortag; zaehlt wie ein Distribution Day.
        "stalling_gewinn_pct": 0.2,
        # Zaehlung nach IBD (ebenda): ab 4 unter Druck, ab 6 Korrektur.
        "dd_druck_ab": 4,
        "dd_korrektur_ab": 6,
        # Follow-through Day (Papier 4.4 Punkt 7): ab dem vierten Tag des
        # Erholungsversuchs ein Anstieg von mindestens 1,25 Prozent bei
        # hoeherem Volumen. Ein Tief zaehlt (eigene Festlegung, IBD nennt
        # keine Zahl) bei einem Schluss unter der 50-Tage-Linie, der der
        # tiefste der letzten 25 Sitzungen ist.
        "ftd_ab_tag": 4,
        "ftd_gewinn_pct": 1.25,
        "ftd_linie_tage": 50,
        "ftd_tief_fenster": 25,
        # McClellan-Oszillator ratio-adjusted (StockCharts ChartSchool).
        "mcclellan_kurz": 19,
        "mcclellan_lang": 39,
        "mcclellan_alpha_kurz": 0.10,
        "mcclellan_alpha_lang": 0.05,
        # Richtung des Summation Index ueber so viele Tage.
        "summation_trend_tage": 5,
        # Fenster fuer A/D-Linie, Hochs-Tiefs-Schnitt und Stockbee-Verhaeltnis.
        "mittel_tage": 10,
        "sma_tage": [20, 50, 200],
        # Neues 52-Wochen-Hoch: ueber dem hoechsten Hoch so vieler Sitzungen davor.
        "hoch_tief_tage": 251,
        # Stockbee Market Monitor, Formeln aus dem Beitrag vom August 2014.
        "stockbee_tages_pct": 4.0,
        "stockbee_min_volumen": 100_000,
        "stockbee_verhaeltnis_tage": [5, 10],
        "stockbee_quartal_tage": 65,
        "stockbee_monat_tage": 20,
        "stockbee_34_tage": 34,
        "stockbee_min_dollarvolumen": 250_000,
        "stockbee_min_kurs_monat": 5.0,
        # Ein Tag mit weniger Aktien als dieser Anteil des ueblichen gilt als
        # unvollstaendig und zaehlt nicht.
        "min_anteil_tag": 0.5,
    },

    # --- Sektor-Rangliste der 36 Branchen-ETFs (R12 bis R17) -------------
    "sektor_rangliste": {
        # R13: Faber-Mittel ueber 1, 3, 6, 9 und 12 Monate (Handelstage).
        "monate_tage": [21, 63, 126, 189, 252],
        # Rang vor 3 und vor 6 Wochen, wie IBD es zeigt.
        "rang_zurueck_tage": [15, 30],
        # R15: Aufsteiger = Eintritt in die ersten fuenf oder Aufstieg um
        # mindestens fuenf Raenge binnen drei Wochen.
        "aufsteiger_top": 5,
        "aufsteiger_raenge": 5,
        "aufsteiger_fenster_tage": 15,
        # R14: fruehe Aufsteiger-Meldung auf Drei-Monats-Basis, getrennt.
        "frueh_fenster_tage": 63,
        # R16: RS-Linie gegen beide Indizes, Aenderung ueber 1, 4, 12 Wochen.
        "linie_wochen": [1, 4, 12],
        "indizes": ["SPY", "QQQ"],
    },

    # --- Abendbericht (R7, R9, R10, R11, Teil 5) --------------------------
    "abendbericht": {
        # R7: eigene Meldung abends nach Handelsschluss, als Bericht
        # gekennzeichnet, niedrige Prioritaet.
        "melden": True,
        "prioritaet": "low",
        # R11: Universum-Kandidaten ab RS 96, getrennt von den Listen.
        "rs_bericht_ab": 96,
        # Teil 5: RS-Linien-Hoch je Aktie hoechstens einmal in zehn
        # Handelstagen.
        "rs_linien_sperre_tage": 10,
        # R9: "gruen bei rotem Markt" heisst Schluss im Plus UND mindestens
        # 80 Prozent der Handelsminuten im Plus; bis der Minutenanteil
        # gebaut ist, gilt der Schluss allein.
        "gruen_minuten_anteil": 0.80,
        # R10: neue Hochs in drei Stufen (52 Wochen, 20 Tage, RS-Linie).
        "hoch_20_tage": 20,
    },

    # --- IBD-Ratings als Naeherung (R20 bis R22, W4) ----------------------
    "ibd_ratings": {
        # R22: Notengrenzen nach der IBD-Kaufregel: A und B obere 40 Prozent,
        # C die Mitte, D und E untere 40 Prozent (Perzentil ab dem die Note
        # gilt).
        "noten": {"A": 80, "B": 60, "C": 40, "D": 20},
        # Antwort 11: acht gekuerzte Quartale.
        "quartale": 8,
        # W7: 14-Wochen-Quartale auf 13 Wochen umrechnen, mit Kennzeichnung.
        "wochen_13_umrechnen": True,
    },

    # --- Fundamentale Kennzahlen aus dem SEC-Fundament (Etappe 4) -----------
    # Gerhard, 13.09.2026, Entscheidung 7: alle 13 Punkte aus Gruppe B;
    # Entscheidung 8: CAN-SLIM-Haekchen, kein Filter. Rechnung in
    # kennzahlen_fundament.py, abgelegt je Aktie in ibd_ratings.json.
    "fundament_kennzahlen": {
        # Entscheidung 8, woertlich: Quartals-EPS ab 25 Prozent, Dreijahres-CAGR
        # ab 25 Prozent, ROE ab 17 Prozent.
        "canslim_eps_quartal_pct": 25.0,
        "canslim_eps_cagr3_pct": 25.0,
        "canslim_roe_pct": 17.0,
        # Wachstum gegen das Vorjahresquartal fuer so viele Quartale (Papier 4.2
        # Punkt 5: "ueber acht Quartale").
        "wachstum_quartale": 8,
        # EPS-Stabilitaet (Papier: "ueber 12 bis 20 Quartale").
        "stabilitaet_min_quartale": 12,
        "stabilitaet_max_quartale": 20,
        # Ab so vielen Tagen gilt ein Quartal als 14-Wochen-Quartal (W7, wie
        # QUARTAL_LANG_TAGE in ibd_ratings.py).
        "quartal_lang_tage": 95,
        # Bilanzwerte gelten als vom selben Stichtag, wenn sie hoechstens so
        # viele Tage auseinanderliegen.
        "stichtag_toleranz_tage": 10,
        # Die Aktienzahl vom Deckblatt taugt fuer die Marktkapitalisierung,
        # solange sie hoechstens so alt ist (ein Quartal, die Einreichungsfrist
        # des Jahresberichts und Spielraum).
        "aktien_hoechstalter_tage": 200,
        # So viele Kalenderjahre des Fundaments braucht die Rechnung: fuenf
        # Jahre Umsatz-CAGR und zwanzig Quartale fuer die Stabilitaet.
        "jahre": 7,
    },

    # --- Scanner der Heliot-App (Mathias, 14.09.2026) ------------------------
    # Nachttabelle scanner_daten.py, Reiter "Scanner" der App. KEINE
    # Vernetzung mit Waechter, Alarmen oder der Scanner-Mappe.
    "scanner": {
        # "Wuerde eine Toleranzabweichung von 5 % jedoch fuers erste
        # akzeptieren" (Recherche 14.09.2026): Schwellen in Prozent oder als
        # Verhaeltnis duerfen um diesen Bruchteil ihres Werts verfehlt werden,
        # die Lage zu gleitenden Durchschnitten um diesen Bruchteil der ATR 14,
        # Mindest- und Hoechstdauern um diesen Bruchteil, auf ganze Tage
        # abgerundet. Zaehlregeln, Richtungen (steigt, faellt) und feste
        # Formbedingungen (Kurs noch in der Box) bleiben streng.
        "toleranz": 0.05,
        "kurs_block": 100,           # Yahoo-Block, 100 wie im RS-Universum
        "historie_tage": 800,        # drei Jahre Handelstage plus Rand
        "archiv_tage": 1098,         # Kalendertage im Kursarchiv, drei Jahre
        "mindest_abdeckung": 0.90,   # darunter heisst der Stand "unvollstaendig"
        "termine_tage": 10,          # Kalendertage voraus im Nasdaq-Kalender
        # Analysten und Quartalsueberraschungen je Aktie: ein Siebtel des
        # Universums je Nacht (gemessen 0,37 s je Abruf, 200 Abrufe ohne
        # Drosselung), dazu wer in den letzten Tagen berichtet hat.
        "rotation_naechte": 7,
        "nach_bericht_tage": 4,
        "abruf_faeden": 4,
        "abruf_fehlergrenze": 0.25,  # mehr Fehler: fuer diese Nacht aufhoeren
        "abruf_mindestproben": 40,
        # HANDELBARKEIT vor jedem Muster (Recherche 14.09.2026: O'Neil kauft
        # ungern unter 15 Dollar, IBD will 20 bis 25 Millionen Dollar
        # Tagesumsatz; Ausgangswerte etwas lockerer). Die App blendet nicht
        # Handelbares in Teil 1 aus, abschaltbar.
        "handelbar": {
            "kurs_min": 10.0,
            "dollarvolumen_min": 10e6,     # mittlerer Tagesumsatz 50 Tage in Dollar
            "historie_min_tage": 252,
        },
        # LANGEWEILE-SPERRE der Darvas Box (Mathias: "wir brauchen irgendeinen
        # Filter, der langweilige Charts aussortiert"). Darvas selbst nahm
        # nur Aktien, deren Jahreshoch mindestens das Doppelte des Jahrestiefs
        # betrug (1964). Dazu: die Aktie bewegt sich (mittlere Tagesspanne),
        # die Box ist mehr als Rauschen (mindestens anderthalb Tagesspannen
        # hoch) und keine tiefe Korrektur (hoechstens 25 Prozent).
        "langeweile": {
            "jahresspanne_min": 2.0,     # Jahreshoch durch Jahrestief
            "adr_min_pct": 2.5,          # mittlere Tagesspanne der letzten 20 Tage
            "box_adr_min": 1.5,          # Boxhoehe in Tagesspannen
            "box_hoehe_max_pct": 25.0,   # Boxhoehe in Prozent der Oberkante
        },
        # RATING 0 bis 100 je Mustertreffer ("die genaue Gewichtung
        # ueberlassen wir vorerst Dir"): Bausteine je 0 bis 1 ueber eine
        # lineare Rampe vom Mindestwert zum Idealwert, gewichtet je Muster
        # (Recherche 14.09.2026: Darvas, Bulkowski, O'Neil, Minervini,
        # Kullamaegi). Fehlt ein Baustein, zaehlen die uebrigen. Ein Treffer
        # nur mit Toleranz kostet Punkte. Ausgangswerte, zu kalibrieren.
        "rating": {
            "toleranz_abzug": 5,
            "rampen": {
                "rs": [70, 95], "hochnaehe": [25.0, 2.0], "vorlauf": [30.0, 100.0],
                "jahresspanne": [1.5, 3.0], "adr": [2.5, 5.0], "adr_deckel": 12.0,
                "liquiditaet": [5e6, 5e7], "austrocknen": [1.0, 0.6], "enge": [1.0, 0.5],
                "nachfrage": [1.5, 2.5], "kaufpunkt_naehe": [5.0, 0.0], "cup_score": [80, 100],
                "ma200_steigt": [21, 105], "box_ideal": [2.0, 8.0], "box_grenzen": [1.5, 12.0],
            },
            "gewichte": {
                "darvas": {"jahresspanne": 15, "rs": 15, "nachfrage": 15, "box": 15, "hochnaehe": 10,
                           "adr": 10, "austrocknen": 10, "enge": 5, "liquiditaet": 5},
                "vcp": {"muster": 25, "austrocknen": 15, "rs": 15, "hochnaehe": 10, "vorlauf": 10,
                        "enge": 10, "nachfrage": 10, "liquiditaet": 5},
                "cup_handle": {"muster": 30, "rs": 15, "nachfrage": 15, "vorlauf": 10, "austrocknen": 10,
                               "hochnaehe": 10, "liquiditaet": 5},
                "rectangle": {"vorlauf": 15, "muster": 15, "rs": 15, "nachfrage": 15, "austrocknen": 10,
                              "hochnaehe": 5, "liquiditaet": 5},
                "htf": {"muster": 50, "austrocknen": 15, "nachfrage": 15, "liquiditaet": 10},
                "htf_innen": {"muster": 50, "austrocknen": 15, "nachfrage": 15, "liquiditaet": 10},
                "trend_template": {"rs": 25, "hochnaehe": 15, "vorlauf": 15, "ma200_steigt": 15, "adr": 10,
                                   "liquiditaet": 10},
                "standard": {"rs": 25, "hochnaehe": 15, "vorlauf": 15, "nachfrage": 15, "adr": 10,
                             "liquiditaet": 10, "austrocknen": 10},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Optionales Übersteuern per Umgebungsvariable (für Tests, ohne Code-Änderung)
# ---------------------------------------------------------------------------

def _aus_env():
    """Liest ausgewählte ENV-Variablen und überschreibt CFG-Werte."""
    # Beispielhafte numerische Übersteuerung
    if "SCANNER_VOL_FENSTER" in os.environ:
        try:
            CFG["volumen"]["fenster_tage"] = int(os.environ["SCANNER_VOL_FENSTER"])
        except ValueError:
            pass


_aus_env()


# ---------------------------------------------------------------------------
# Selbstprüfung: fängt Widersprüche in der Config ab
# ---------------------------------------------------------------------------

def letzter_putz_tag(jetzt=None):
    """ISO-Datum des jüngsten Freitags-Putzes (Freitag 16:02 New York),
    der bereits VORBEI ist. Steht der heutige Putz noch aus, zählt der
    der Vorwoche.

    Das ist die WOCHENGRENZE des ganzen Systems: Alarme, Melde-Gedächtnis
    des Wächters und das Gesetzt-Gedächtnis des Bots gelten jeweils bis
    hierher. Die Berechnung stand vorher dreimal im Code — genau die Art
    stiller Uneinheitlichkeit, die config.py beseitigen soll.

    jetzt: ein Zeitpunkt mit Zeitzone, fuer Pruefungen und den
    Wochenputz (wochenputz.py, 13.09.2026); ohne Angabe gilt jetzt."""
    from datetime import datetime, timedelta
    try:
        from zoneinfo import ZoneInfo
        _ny = ZoneInfo(CFG["betrieb"]["zeitzone_boerse"])
        jetzt = jetzt.astimezone(_ny) if jetzt else datetime.now(_ny)
    except Exception:
        jetzt = jetzt or datetime.now()
    d = jetzt.date()
    rueck = (d.weekday() - 4) % 7          # Montag=0 … Freitag=4
    freitag = d - timedelta(days=rueck)
    if rueck == 0 and jetzt.hour * 60 + jetzt.minute < 16 * 60 + 2:
        freitag -= timedelta(days=7)
    return freitag.isoformat()


# ---------------------------------------------------------------------------
# Schwellenvergleiche
# ---------------------------------------------------------------------------

# WICHTIG, und ausdrücklich NICHT kosmetisch. 120,0 geteilt durch 100,0
# minus 1 ergibt in Gleitkomma 0,19999999999999996, nicht 0,20. Ein
# Vergleich "größer gleich 0,20" scheitert damit ausgerechnet am exakten
# Grenzfall — also an genau dem Fall, den die Regel treffen soll.
#
# Gefunden am 02.08.2026 in der Volumensignatur zu Kapitel 9 (dort
# rechnete sich exaktes Normaltempo zu 2,2 mal 10 hoch minus 14 statt zu
# null). Gerhard ist am 05.08.2026 beim Bauen des Exit-Moduls in
# denselben Fehler gelaufen und schlägt diese zentrale Stelle vor.
#
# Betroffen ist potenziell JEDER Schwellenvergleich im System: Lücke ab
# 7 %, Volumen ab 3×, Rücksetzer bis 45 %, RS ab 90 und so weiter —
# überall dort, wo ein Wert aus einer Division stammt und gegen eine
# runde Zahl geprüft wird.
SCHWELLEN_SPIEL = 1e-9


def mind_erreicht(wert, schwelle):
    """Ist der Wert mindestens so groß wie die Schwelle?

    Schließt den exakten Grenzfall zuverlässig ein. None ergibt False —
    ein fehlender Wert erreicht keine Schwelle."""
    if wert is None or schwelle is None:
        return False
    return wert >= schwelle - SCHWELLEN_SPIEL


def hoechstens(wert, schwelle):
    """Die Gegenrichtung: Bleibt der Wert höchstens bei der Schwelle?"""
    if wert is None or schwelle is None:
        return False
    return wert <= schwelle + SCHWELLEN_SPIEL


def pruefe_config():
    """Wirft AssertionError bei unplausiblen/widersprüchlichen Werten.
    Beim Start jedes Moduls einmal aufrufen — fängt Tippfehler früh."""
    assert abs(sum(CFG["lookback"]["rs_gewichte"]) - 1.0) < 1e-9, \
        "RS-Gewichte müssen in Summe 1,0 ergeben"
    assert len(CFG["lookback"]["rs_quartale"]) == len(CFG["lookback"]["rs_gewichte"]), \
        "RS: gleich viele Quartale wie Gewichte"
    assert 0.0 < float(CFG["lookback"]["rs_kappung"]) <= 5.0, \
        "RS-Kappung: eine Rendite-Obergrenze je Zeitraum, als Bruchteil (0,5 heisst plus 50 Prozent)"
    assert CFG["volumen"]["fenster_tage"] > 0
    # Gerhards Antworten vom 12.09.2026
    u = CFG["rs_universum"]
    assert 0.0 < u["mindest_abdeckung"] <= 1.0, "RS-Universum: Mindestabdeckung zwischen 0 und 1"
    assert 1 <= u["sehr_gut_ab"] <= 99, "RS-Universum: 'sehr gut' braucht ein Perzentil 1 bis 99"
    assert u["historie_tage"] >= max(CFG["lookback"]["rs_quartale"]), \
        "RS-Universum: die Historie muss das laengste RS-Quartal decken"
    assert u["mindestkurs"] > 0 and u["mindest_dollarvolumen"] > 0
    t = CFG["technik"]
    assert t["adr_tage"] >= 2 and len(t["volatilitaet_tage"]) == 2 and min(t["volatilitaet_tage"]) >= 2, \
        "Technik: ADR und Volatilitaet ueber mindestens zwei Tage"
    assert all(w == "jahr" or (isinstance(w, int) and w >= 1) for w in t["wertentwicklung_tage"].values()), \
        "Technik: Wertentwicklung in Handelstagen oder 'jahr'"
    assert len(t["rsi_tage"]) == 2 and min(t["rsi_tage"]) >= 2, "Technik: RSI ueber zwei Fenster mit je mindestens zwei Tagen"
    assert t["weinstein_flach_pct"] >= 0 and t["vergleich_wochen"] >= 1 and t["weinstein_vorlauf_wochen"] >= 1
    assert t["mansfield_wochen"] + t["vergleich_wochen"] <= 60,         "Technik: Mansfield RS samt Vergleich muss in die 14 Monate des Abrufs passen"
    assert t["beta_tage"] < u["historie_tage"] + 30 and max(t["sma_tage"]) <= u["historie_tage"]
    assert t["allzeithoch_abruf_tage"] >= 1 and 0 <= t["allzeithoch_split_toleranz"] < 0.1
    assert t["split_verdacht_faktor"] > 1 and t["split_verdacht_dollarvolumen"] >= 1 and t["split_ereignis_tage"] >= 1
    mb = CFG["marktbreite"]
    assert mb["dd_verlust_pct"] > 0 and mb["dd_fenster"] >= 1 and mb["dd_verfall_pct"] > 0, \
        "Marktbreite: Distribution Days brauchen Verlust, Fenster und Verfall"
    assert 0 < mb["stalling_gewinn_pct"] and 1 <= mb["dd_druck_ab"] < mb["dd_korrektur_ab"]
    assert mb["ftd_ab_tag"] >= 1 and mb["ftd_gewinn_pct"] > 0 and mb["ftd_linie_tage"] >= 2 and mb["ftd_tief_fenster"] >= 2
    assert 1 <= mb["mcclellan_kurz"] < mb["mcclellan_lang"] and 0 < mb["mcclellan_alpha_lang"] < mb["mcclellan_alpha_kurz"] < 1
    assert 1 <= mb["summation_trend_tage"] <= mb["mittel_tage"] and max(mb["stockbee_verhaeltnis_tage"]) <= mb["mittel_tage"], \
        "Marktbreite: Summation-Richtung und Stockbee-Verhaeltnis muessen ins Zehn-Tage-Fenster passen"
    assert max(mb["sma_tage"]) <= u["historie_tage"] and mb["hoch_tief_tage"] <= u["historie_tage"]
    assert 0 < mb["min_anteil_tag"] < 1 and mb["stockbee_min_volumen"] >= 0 and mb["stockbee_min_dollarvolumen"] >= 0
    assert min(mb["stockbee_quartal_tage"], mb["stockbee_monat_tage"], mb["stockbee_34_tage"]) >= 2 and mb["stockbee_min_kurs_monat"] >= 0
    s = CFG["scanner"]
    assert 0.0 <= s["toleranz"] < 0.5, "Scanner: Toleranz als Bruchteil zwischen 0 und 0,5"
    assert s["historie_tage"] >= 760, "Scanner: drei Jahre Handelstage brauchen mindestens 760 Tage"
    assert s["rotation_naechte"] >= 1 and s["abruf_faeden"] >= 1
    assert 0.0 < s["mindest_abdeckung"] <= 1.0
    fk = CFG["fundament_kennzahlen"]
    assert fk["canslim_eps_quartal_pct"] > 0 and fk["canslim_eps_cagr3_pct"] > 0 and fk["canslim_roe_pct"] > 0
    assert fk["wachstum_quartale"] >= 3 and 3 <= fk["stabilitaet_min_quartale"] <= fk["stabilitaet_max_quartale"] <= 24, \
        "Fundament: Beschleunigung braucht drei Quartale, die Stabilitaet hoechstens sechs Jahre"
    assert 91 < fk["quartal_lang_tage"] < 100 and 0 <= fk["stichtag_toleranz_tage"] <= 45
    assert fk["aktien_hoechstalter_tage"] >= 100 and fk["jahre"] >= 6, \
        "Fundament: die Umsatz-CAGR ueber fuenf Jahre braucht mindestens sechs Kalenderjahre"
    n = CFG["ibd_ratings"]["noten"]
    assert n["A"] > n["B"] > n["C"] > n["D"] > 0, "IBD-Noten: Grenzen muessen fallen (A ueber B ueber C ueber D)"
    assert CFG["gap_and_go"]["einstieg_grenze"] <= CFG["betrieb"]["nachlauf_grenze"], \
        "W2: die engere Einstiegsgrenze darf das allgemeine Fenster nicht ueberschreiten"
    assert 570 <= CFG["betrieb"]["schlussnahe_minute"] <= 959, \
        "M1: schlussnahe Minute muss im Handelstag liegen (570 bis 959)"
    assert CFG["sektor_rangliste"]["aufsteiger_fenster_tage"] in CFG["sektor_rangliste"]["rang_zurueck_tage"], \
        "Sektor-Rangliste: das Aufsteiger-Fenster muss einer der Rueckblick-Tage sein"
    return True


if __name__ == "__main__":
    pruefe_config()
    print("config.py — Selbstprüfung bestanden. Alle Werte konsistent.")
    print(f"  Volumen-Fenster: {CFG['volumen']['fenster_tage']} Tage (einheitlich)")
