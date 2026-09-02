#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fundament, Phase 1: Normalisierung der amtlichen XBRL-Fakten der SEC
(companyfacts) je Firma in Quartals- und Jahresreihen der Kernkennzahlen.

GERHARDS AUFTRAG (01.09.2026, F1 bis F6): alle SEC-gelisteten Firmen,
volle Historie ab 2009, Rohdaten ALLER Felder mitfuehren, auslaendische
Listings mitnehmen und kennzeichnen, Validierung gegen echte Berichte hat
Vorrang vor Tempo.

WAS DIESES MODUL TUT (ohne Netz, reine Rechenlogik):
  normalisiere(firma) nimmt das companyfacts-JSON einer Firma (Struktur
  {"cik", "entityName", "facts": {"us-gaap": {Tag: {"units": {Einheit:
  [Fakt, ...]}}}, "dei": ..., "ifrs-full": ...}}) und liefert
  (metadaten, zeilen). Jede Zeile ist EIN Wert EINER Kennzahl fuer EINE
  Periode, mit beiden Fassungen:
    wert_erst   = wie ZUERST eingereicht (das, was der Markt damals sah),
    wert_letzt  = wie ZULETZT eingereicht (Restatements, Amendments),
  dazu Formular, Einreichungsdatum und Aktennummer beider Fassungen.

DIE VIER FALLEN DER SEC-DATEN, die hier abgefangen werden:
  1. Wiederholung: Jeder 10-Q wiederholt die Vorjahresperiode als
     Vergleich. Derselbe Wert steht deshalb in bis zu fuenf Einreichungen.
     Zusammengefuehrt wird ueber die PERIODE (Start/Ende), nicht ueber
     die Einreichung.
  2. fy/fp luegen: Die Felder fy und fp eines Fakts beschreiben die
     EINREICHUNG, nicht die Periode des Fakts (der Vergleichswert Q1 2024
     im 10-Q Q1 2025 traegt fy 2025). Die Fiskalperiode wird deshalb nur
     aus der Einreichung genommen, deren HAUPTPERIODE der Fakt ist
     (Periodenende = spaetestes Datum der Einreichung).
  3. Q4 fehlt: Der 10-K enthaelt fuer Flussgroessen (Umsatz, Gewinn,
     Cashflow) nur den Jahreswert. Das vierte Quartal wird als Jahr minus
     Neunmonatswert (oder minus Summe der drei Quartale) BERECHNET und als
     solches gekennzeichnet. Nicht additive Groessen (Ergebnis je Aktie,
     Aktienzahlen) werden nie berechnet.
  4. Tag-Wechsel: Firmen wechselten die Konzepte (SalesRevenueNet bis 2017,
     RevenueFromContractWithCustomer... ab 2018). Je Kennzahl gilt eine
     Kaskade von Konzepten, angewandt JE PERIODE.

KENNZEICHNUNG (F4): metadaten["filer_typ"] unterscheidet inland_usgaap,
ausland_usgaap (20-F/40-F-Einreicher mit US-GAAP) und ausland_ifrs
(Taxonomie ifrs-full). Jede Zeile traegt quelle = "amtlich" oder
"berechnet" sowie Taxonomie und Konzept. Werte in anderen Waehrungen als
USD werden NICHT umgerechnet, sondern mit ihrer Einheit ausgegeben.

Aufruf:
  python fundament_normalisieren.py --selbsttest
"""

import datetime as dt
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# Kennzahlen-Register (Erstliste fuer Gerhards 40er-Entscheid nach Phase 1)
# ---------------------------------------------------------------------------
# art: "dauer" (Flussgroesse mit Start und Ende) oder "bestand" (Stichtag)
# additiv: Q4 darf aus Jahr minus Vorquartalen berechnet werden
# tags: Konzepte in Prioritaetsordnung; ohne Praefix = us-gaap,
#       "dei:" = Deckblatt-Taxonomie, "ifrs:" = ifrs-full

KENNZAHLEN = {
    "umsatz": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet", "SalesRevenueGoodsNet", "SalesRevenueServicesNet",
        "RevenuesNetOfInterestExpense", "TotalRevenuesAndOtherIncome",
        "ifrs:Revenue"]),
    "umsatzkosten": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
        "CostOfServices",
        "CostOfGoodsAndServicesSoldExcludingDepreciationDepletionAndAmortization",
        "ifrs:CostOfSales"]),
    "bruttogewinn": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "GrossProfit", "ifrs:GrossProfit"]),
    "operatives_ergebnis": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "OperatingIncomeLoss", "ifrs:ProfitLossFromOperatingActivities"]),
    "ergebnis_vor_steuern": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
        "ifrs:ProfitLossBeforeTax"]),
    "steuern": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "IncomeTaxExpenseBenefit", "ifrs:IncomeTaxExpenseContinuingOperations"]),
    "nettogewinn": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "NetIncomeLoss", "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "IncomeLossFromContinuingOperations", "ifrs:ProfitLoss"]),
    "minderheiten_ergebnis": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "NetIncomeLossAttributableToNoncontrollingInterest",
        "ifrs:ProfitLossAttributableToNoncontrollingInterests"]),
    "eps_verwaessert": dict(art="dauer", einheit="USD/shares", additiv=False, tags=[
        "EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted",
        "ifrs:DilutedEarningsLossPerShare"]),
    "eps_basis": dict(art="dauer", einheit="USD/shares", additiv=False, tags=[
        "EarningsPerShareBasic", "EarningsPerShareBasicAndDiluted",
        "ifrs:BasicEarningsLossPerShare"]),
    "aktien_verwaessert": dict(art="dauer", einheit="shares", additiv=False, tags=[
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
        "ifrs:WeightedAverageNumberOfDilutedSharesOutstanding"]),
    "aktien_basis": dict(art="dauer", einheit="shares", additiv=False, tags=[
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
        "ifrs:WeightedAverageShares"]),
    "forschung_entwicklung": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        "ifrs:ResearchAndDevelopmentExpense"]),
    "vertrieb_verwaltung": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "SellingGeneralAndAdministrativeExpense",
        "ifrs:SellingGeneralAndAdministrativeExpense"]),
    "betriebsaufwand": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "OperatingExpenses", "CostsAndExpenses"]),
    "zinsaufwand": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "InterestExpense", "InterestExpenseNonoperating",
        "InterestExpenseDebt", "ifrs:InterestExpense"]),
    "abschreibungen": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet", "Depreciation",
        "ifrs:DepreciationAndAmortisationExpense"]),
    "aktienbasierte_verguetung": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]),
    "operativer_cashflow": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        "ifrs:CashFlowsFromUsedInOperatingActivities"]),
    "investitionen": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "ifrs:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"]),
    "investitions_cashflow": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
        "ifrs:CashFlowsFromUsedInInvestingActivities"]),
    "finanzierungs_cashflow": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "NetCashProvidedByUsedInFinancingActivities",
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
        "ifrs:CashFlowsFromUsedInFinancingActivities"]),
    "dividenden_gezahlt": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "PaymentsOfDividends", "PaymentsOfDividendsCommonStock",
        "ifrs:DividendsPaidClassifiedAsFinancingActivities"]),
    "aktienrueckkauf": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "PaymentsForRepurchaseOfCommonStock"]),
    # Bestandsgroessen (Stichtag)
    "bilanzsumme": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "Assets", "ifrs:Assets"]),
    "umlaufvermoegen": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "AssetsCurrent", "ifrs:CurrentAssets"]),
    "kasse": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash",
        "ifrs:CashAndCashEquivalents"]),
    "kurzfristige_anlagen": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "ShortTermInvestments", "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]),
    "forderungen": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
        "ifrs:TradeAndOtherCurrentReceivables"]),
    "vorraete": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "InventoryNet", "ifrs:Inventories"]),
    "sachanlagen": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "PropertyPlantAndEquipmentNet", "ifrs:PropertyPlantAndEquipment"]),
    "goodwill": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "Goodwill", "ifrs:Goodwill"]),
    "verbindlichkeiten": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "Liabilities", "ifrs:Liabilities"]),
    "kurzfristige_verbindlichkeiten": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "LiabilitiesCurrent", "ifrs:CurrentLiabilities"]),
    "langfristige_schulden": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "LongTermDebtNoncurrent", "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
        "ifrs:NoncurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"]),
    "kurzfristige_schulden": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings",
        "ifrs:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"]),
    "eigenkapital": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "ifrs:Equity"]),
    "gewinnruecklagen": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "RetainedEarningsAccumulatedDeficit", "ifrs:RetainedEarnings"]),
    "aktien_ausstehend": dict(art="bestand", einheit="shares", additiv=False, tags=[
        "dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding",
        "ifrs:NumberOfSharesOutstanding"]),
    "streubesitz_wert": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "dei:EntityPublicFloat"]),
    # --- Sonderbranchen (Gerhards Entscheid F14 vom 02.09.2026: gleich mit
    # eigenen Zeilen, nicht erst in einer zweiten Runde) ---
    # Banken: Der "Umsatz" einer Bank sind ihre Nettoertraege (Kaskade
    # oben, RevenuesNetOfInterestExpense); dazu die Bausteine.
    "zinsertrag": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "InterestAndDividendIncomeOperating", "InterestIncomeOperating",
        "ifrs:InterestRevenueCalculatedUsingEffectiveInterestMethod"]),
    "zinsueberschuss": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "InterestIncomeExpenseNet", "ifrs:NetInterestIncome"]),
    "provisionsertrag": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "NoninterestIncome", "ifrs:FeeAndCommissionIncome"]),
    "verwaltungsaufwand_bank": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "NoninterestExpense"]),
    "risikovorsorge": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "ProvisionForLoanLeaseAndOtherLosses", "ProvisionForCreditLosses",
        "CreditLossExpense", "ProvisionForLoanLossesExpensed",
        "ifrs:ImpairmentLossOnFinancialAssets"]),
    "einlagen": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "Deposits", "ifrs:DepositsFromCustomers"]),
    "kredite": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "LoansAndLeasesReceivableNetReportedAmount",
        "LoansAndLeasesReceivableNetOfDeferredIncome", "NotesReceivableNet",
        "ifrs:LoansAndAdvancesToCustomers"]),
    "kernkapitalquote": dict(art="bestand", einheit="pure", additiv=False, tags=[
        "CommonEquityTierOneCapitalToRiskWeightedAssets",
        "TierOneRiskBasedCapitalToRiskWeightedAssets"]),
    # Versicherer
    "praemien_verdient": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "PremiumsEarnedNet", "PremiumsEarnedNetPropertyAndCasualty",
        "ifrs:RevenueFromInsuranceContractsIssuedWithoutReductionForReinsuranceHeld"]),
    "praemien_gebucht": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "PremiumsWrittenNet"]),
    "schadenaufwand": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "PolicyholderBenefitsAndClaimsIncurredNet",
        "IncurredClaimsPropertyCasualtyAndLiability", "BenefitsLossesAndExpenses"]),
    "kapitalanlageertrag": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "NetInvestmentIncome"]),
    # Immobiliengesellschaften (REITs). FFO ist kein amtliches Konzept und
    # wird in der Abfrageschicht nach NAREIT aus Nettogewinn, Abschreibungen,
    # Wertminderungen und Verkaufsgewinnen BERECHNET; hier nur die Bausteine.
    "mieterloese": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "OperatingLeaseLeaseIncome", "OperatingLeasesIncomeStatementLeaseRevenue",
        "RealEstateRevenueNet", "ifrs:RentalIncome"]),
    "immobilien_netto": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "RealEstateInvestmentPropertyNet", "ifrs:InvestmentProperty"]),
    "immobilien_anschaffungskosten": dict(art="bestand", einheit="USD", additiv=False, tags=[
        "RealEstateInvestmentPropertyAtCost"]),
    "wertminderung_immobilien": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "ImpairmentOfRealEstate"]),
    "gewinn_immobilienverkauf": dict(art="dauer", einheit="USD", additiv=True, tags=[
        "GainLossOnSaleOfProperties", "GainsLossesOnSalesOfInvestmentRealEstate",
        "GainLossOnSalesOfRealEstate"]),
}

AUSLAND_FORMEN = ("20-F", "40-F", "6-K", "20-F/A", "40-F/A", "6-K/A")


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def _datum(s):
    return dt.date.fromisoformat(s) if s else None


def _periodentyp(start, ende):
    """Q, H, 9M, FY oder None (nach der Dauer in Tagen; 52/53-Wochen-
    Geschaeftsjahre liegen innerhalb der Toleranzen)."""
    tage = (ende - start).days + 1
    if 80 <= tage <= 100:
        return "Q"
    if 170 <= tage <= 195:
        return "H"
    if 255 <= tage <= 290:
        return "9M"
    if 350 <= tage <= 380:
        return "FY"
    return None


def _quartalsende_naechst(ende):
    kandidaten = [dt.date(j, m, d)
                  for j in (ende.year - 1, ende.year, ende.year + 1)
                  for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))]
    naechst = min(kandidaten, key=lambda k: abs((k - ende).days))
    if abs((naechst - ende).days) > 45:
        return None
    return naechst


def kalender_rahmen(ende, typ):
    """Kalenderzuordnung wie die SEC-Frames, aber ohne Luecken: das
    naechstgelegene Kalenderquartalsende zaehlt. typ: Q, FY oder
    None (Bestand). Ein Geschaeftsjahr, das nicht im Dezember endet,
    bekommt die Form CY2025Q3FY (endet im dritten Kalenderquartal)."""
    q_ende = _quartalsende_naechst(ende)
    if q_ende is None:
        return None
    q = (q_ende.month - 1) // 3 + 1
    if typ == "FY":
        return f"CY{q_ende.year}" if q == 4 else f"CY{q_ende.year}Q{q}FY"
    if typ == "Q":
        return f"CY{q_ende.year}Q{q}"
    return f"CY{q_ende.year}Q{q}I"


def _taxonomie(tag):
    if tag.startswith("dei:"):
        return "dei", tag[4:]
    if tag.startswith("ifrs:"):
        return "ifrs-full", tag[5:]
    return "us-gaap", tag


def cik_zahl(firma):
    """Die CIK als Zahl. Die API liefert sie als Zahl, das Bulk-Archiv als
    zehnstellige Zeichenkette mit fuehrenden Nullen ('0000022606')."""
    roh = firma.get("cik")
    try:
        return int(str(roh).strip())
    except (TypeError, ValueError):
        return None


def alle_fakten(firma):
    """Generator ueber ALLE Fakten aller Taxonomien (Rohdaten, F2)."""
    cik = cik_zahl(firma)
    for tax, konzepte in (firma.get("facts") or {}).items():
        for name, inhalt in (konzepte or {}).items():
            for einheit, liste in (inhalt.get("units") or {}).items():
                for e in liste or []:
                    yield {"cik": cik, "taxonomie": tax, "tag": name,
                           "einheit": einheit, "start": e.get("start"),
                           "end": e.get("end"), "val": e.get("val"),
                           "accn": e.get("accn"), "fy": e.get("fy"),
                           "fp": e.get("fp"), "form": e.get("form"),
                           "filed": e.get("filed"), "frame": e.get("frame")}


def _periodenende_je_einreichung(firma):
    """Hauptperiode je Aktennummer: das HAEUFIGSTE Enddatum ihrer us-gaap-
    und ifrs-Fakten (bei Gleichstand das spaetere). Nicht das spaeteste:
    Deckblatt-Fakten der dei-Taxonomie tragen das Datum kurz vor der
    Einreichung (Apple: Aktienzahl per 18.07. im Quartal bis 28.06.) und
    haetten die Fiskalzuordnung aller Werte verfaelscht (Befund der
    ersten Probe-Validierung, 02.09.2026)."""
    zaehler = defaultdict(lambda: defaultdict(int))
    for f in alle_fakten(firma):
        if not f["accn"] or not f["end"] or f["taxonomie"] == "dei":
            continue
        zaehler[f["accn"]][f["end"]] += 1
    return {accn: max(je_ende, key=lambda e: (je_ende[e], e))
            for accn, je_ende in zaehler.items()}


# ---------------------------------------------------------------------------
# Kern
# ---------------------------------------------------------------------------

def _sammle(firma, kennzahl):
    """Alle Vorkommen der Kaskaden-Konzepte, gruppiert nach Periode.
    Rueckgabe: {(start, end, einheit): [vorkommen, ...]}"""
    spez = KENNZAHLEN[kennzahl]
    facts = firma.get("facts") or {}
    gruppen = defaultdict(list)
    for rang, tag in enumerate(spez["tags"]):
        tax, name = _taxonomie(tag)
        inhalt = (facts.get(tax) or {}).get(name)
        if not inhalt:
            continue
        for einheit, liste in (inhalt.get("units") or {}).items():
            for e in liste or []:
                ende = e.get("end")
                if not ende or e.get("val") is None:
                    continue
                start = e.get("start") if spez["art"] == "dauer" else None
                if spez["art"] == "dauer" and not start:
                    continue
                if spez["art"] == "bestand" and e.get("start"):
                    continue
                gruppen[(start, ende, einheit)].append({
                    "rang": rang, "tax": tax, "tag": name, "val": e["val"],
                    "accn": e.get("accn"), "fy": e.get("fy"), "fp": e.get("fp"),
                    "form": e.get("form") or "", "filed": e.get("filed") or "",
                    "frame": e.get("frame")})
    return gruppen


def _fiskal(vorkommen, enden, periode_ende):
    """Fiskaljahr und -periode aus der Einreichung, deren Hauptperiode
    der Fakt ist; sonst aus der Vorjahres-Vergleichsposition (gleiche
    Periode, Jahr minus eins); sonst (None, None)."""
    for v in sorted(vorkommen, key=lambda x: x["filed"]):
        if v["accn"] and enden.get(v["accn"]) == periode_ende and v["fy"]:
            return v["fy"], v["fp"]
    pe = _datum(periode_ende)
    for v in sorted(vorkommen, key=lambda x: x["filed"]):
        haupt = _datum(enden.get(v["accn"])) if v["accn"] else None
        if haupt and v["fy"] and 340 <= (haupt - pe).days <= 400:
            return v["fy"] - 1, v["fp"]
    return None, None


def _zeile(cik, kennzahl, spez, schluessel, vorkommen, enden, typ):
    start, ende, einheit = schluessel
    bester_rang = min(v["rang"] for v in vorkommen)
    gewaehlt = [v for v in vorkommen if v["rang"] == bester_rang]
    nach_filed = sorted(gewaehlt, key=lambda v: (v["filed"], v["accn"] or ""))
    erst, letzt = nach_filed[0], nach_filed[-1]
    fy, fp = _fiskal(gewaehlt, enden, ende)
    if typ == "Q" and fp == "FY":
        fp = "Q4"
    frame = next((v["frame"] for v in vorkommen if v["frame"]), None)
    ende_d = _datum(ende)
    return {
        "cik": cik, "kennzahl": kennzahl, "typ": typ, "start": start, "end": ende,
        "fiskaljahr": fy, "fiskalperiode": fp if typ != "FY" else "FY",
        "kalender": frame or kalender_rahmen(ende_d, typ if typ in ("Q", "FY") else None),
        "kalender_quelle": "sec_frame" if frame else "berechnet",
        "wert_erst": erst["val"], "filed_erst": erst["filed"], "form_erst": erst["form"],
        "accn_erst": erst["accn"],
        "wert_letzt": letzt["val"], "filed_letzt": letzt["filed"],
        "form_letzt": letzt["form"], "accn_letzt": letzt["accn"],
        "restated": erst["val"] != letzt["val"],
        "taxonomie": erst["tax"], "tag": erst["tag"], "einheit": einheit,
        "quelle": "amtlich", "n_einreichungen": len({v["accn"] for v in gewaehlt}),
    }


def _berechnet(cik, kennzahl, basis, minus, start, ende, fp, fy, einheit, typ="Q"):
    """Abgeleitete Periode (Jahr minus Neunmonate usw.); beide Fassungen
    aus den jeweiligen Fassungen der Bestandteile."""
    def diff(feld):
        werte = [basis[feld]] + [-m[feld] for m in minus]
        if any(w is None for w in werte):
            return None
        return round(sum(werte), 6)
    ende_d = _datum(ende)
    return {
        "cik": cik, "kennzahl": kennzahl, "typ": typ, "start": start, "end": ende,
        "fiskaljahr": fy, "fiskalperiode": fp,
        "kalender": kalender_rahmen(ende_d, "Q"), "kalender_quelle": "berechnet",
        "wert_erst": diff("wert_erst"), "filed_erst": basis["filed_erst"],
        "form_erst": basis["form_erst"], "accn_erst": basis["accn_erst"],
        "wert_letzt": diff("wert_letzt"), "filed_letzt": basis["filed_letzt"],
        "form_letzt": basis["form_letzt"], "accn_letzt": basis["accn_letzt"],
        "restated": diff("wert_erst") != diff("wert_letzt"),
        "taxonomie": basis["taxonomie"], "tag": basis["tag"], "einheit": einheit,
        "quelle": "berechnet", "n_einreichungen": basis["n_einreichungen"],
    }


def _folgetag(datum_s):
    return (_datum(datum_s) + dt.timedelta(days=1)).isoformat()


def _ableiten(cik, kennzahl, zeilen_typ, einheit):
    """Fehlende Quartale aus kumulierten Werten: Q2 = H1 minus Q1,
    Q3 = 9M minus H1 (oder minus Q1 minus Q2), Q4 = FY minus 9M (oder
    minus Q1 minus Q2 minus Q3). Nur fuer additive Kennzahlen."""
    q = {(z["start"], z["end"]): z for z in zeilen_typ.get("Q", [])}
    h = {(z["start"], z["end"]): z for z in zeilen_typ.get("H", [])}
    n = {(z["start"], z["end"]): z for z in zeilen_typ.get("9M", [])}
    fy = {(z["start"], z["end"]): z for z in zeilen_typ.get("FY", [])}
    q_nach_ende = {z["end"]: z for z in q.values()}
    neu = []

    def quartale_ab(start, bis):
        """Kette Q1, Q2, ... ab start, jedes beginnt am Folgetag des
        vorigen, solange das Ende vor bis liegt."""
        kette, s = [], start
        while True:
            treffer = [z for (st, en), z in q.items() if st == s and en < bis]
            if not treffer:
                break
            z = min(treffer, key=lambda x: x["end"])
            kette.append(z)
            s = _folgetag(z["end"])
        return kette

    def fehlt(ende):
        return ende not in q_nach_ende

    for (s, e), zh in h.items():
        if fehlt(e):
            kette = quartale_ab(s, e)
            if len(kette) == 1:
                z = _berechnet(cik, kennzahl, zh, kette, _folgetag(kette[-1]["end"]), e,
                               "Q2", zh["fiskaljahr"], einheit)
                neu.append(z); q_nach_ende[e] = z
    for (s, e), zn in n.items():
        if fehlt(e):
            kette = quartale_ab(s, e)
            if len(kette) == 2:
                z = _berechnet(cik, kennzahl, zn, kette, _folgetag(kette[-1]["end"]), e,
                               "Q3", zn["fiskaljahr"], einheit)
                neu.append(z); q_nach_ende[e] = z
            else:
                hs = [zh for (st, en), zh in h.items() if st == s and en < e]
                if len(hs) == 1:
                    z = _berechnet(cik, kennzahl, zn, hs, _folgetag(hs[0]["end"]), e,
                                   "Q3", zn["fiskaljahr"], einheit)
                    neu.append(z); q_nach_ende[e] = z
    for (s, e), zf in fy.items():
        if fehlt(e):
            ns = [zn for (st, en), zn in n.items() if st == s and en < e]
            if len(ns) == 1:
                z = _berechnet(cik, kennzahl, zf, ns, _folgetag(ns[0]["end"]), e,
                               "Q4", zf["fiskaljahr"], einheit)
                neu.append(z); q_nach_ende[e] = z
                continue
            kette = quartale_ab(s, e)
            if len(kette) == 3:
                z = _berechnet(cik, kennzahl, zf, kette, _folgetag(kette[-1]["end"]), e,
                               "Q4", zf["fiskaljahr"], einheit)
                neu.append(z); q_nach_ende[e] = z
    return neu


def _nettogewinn_ohne_minderheiten(zeilen):
    """Firmen mit Minderheitsanteilen taggen fuer das Konzernergebnis oft
    nur ProfitLoss (samt Minderheiten) und den Minderheitenanteil
    getrennt; NetIncomeLoss (der Anteil der Aktionaere) fehlt dann. Wo
    die Kaskade auf ProfitLoss ausgewichen ist und ein Minderheiten-Wert
    derselben Periode vorliegt, wird der Aktionaersanteil BERECHNET
    (Befund IES Holdings, erste Probe-Validierung 02.09.2026)."""
    minderheiten = {(z["start"], z["end"], z["einheit"]): z for z in zeilen
                    if z["kennzahl"] == "minderheiten_ergebnis"}
    for z in zeilen:
        if z["kennzahl"] != "nettogewinn" or z["tag"] != "ProfitLoss":
            continue
        m = minderheiten.get((z["start"], z["end"], z["einheit"]))
        if m is None:
            continue
        for feld in ("wert_erst", "wert_letzt"):
            if z[feld] is not None and m[feld] is not None:
                z[feld] = round(z[feld] - m[feld], 6)
        z["restated"] = z["wert_erst"] != z["wert_letzt"]
        z["tag"] = "ProfitLoss minus NetIncomeLossAttributableToNoncontrollingInterest"
        z["quelle"] = "berechnet"


def filer_typ(firma):
    facts = firma.get("facts") or {}
    formen = set()
    for f in alle_fakten(firma):
        if f["form"]:
            formen.add(f["form"])
    hat_ifrs = bool(facts.get("ifrs-full"))
    auslaendisch = any(fm in AUSLAND_FORMEN for fm in formen)
    # IFRS-Fakten fuehrt nur, wer als auslaendischer Emittent einreicht;
    # daneben liegende us-gaap- oder dei-Reste aendern daran nichts.
    if hat_ifrs:
        return "ausland_ifrs"
    if auslaendisch:
        return "ausland_usgaap"
    return "inland_usgaap"


def normalisiere(firma, kennzahlen=None):
    """(metadaten, zeilen) fuer eine Firma. zeilen enthaelt Quartals-
    (typ Q) und Jahreszeilen (typ FY) aller Kennzahlen; Halbjahres- und
    Neunmonatswerte dienen nur der Ableitung und werden nicht ausgegeben."""
    cik = cik_zahl(firma)
    enden = _periodenende_je_einreichung(firma)
    zeilen = []
    waehrungen = set()
    for kennzahl in (kennzahlen or KENNZAHLEN):
        spez = KENNZAHLEN[kennzahl]
        gruppen = _sammle(firma, kennzahl)
        je_einheit_typ = defaultdict(lambda: defaultdict(list))
        for schluessel, vorkommen in gruppen.items():
            start, ende, einheit = schluessel
            if spez["art"] == "dauer":
                typ = _periodentyp(_datum(start), _datum(ende))
                if typ is None:
                    continue
            else:
                typ = "B"
            je_einheit_typ[einheit][typ].append(
                _zeile(cik, kennzahl, spez, schluessel, vorkommen, enden, typ))
        for einheit, nach_typ in je_einheit_typ.items():
            if kennzahl == "umsatz" and einheit != "USD":
                waehrungen.add(einheit)
            if spez["art"] == "dauer" and spez["additiv"]:
                nach_typ["Q"].extend(_ableiten(cik, kennzahl, nach_typ, einheit))
            for typ in ("Q", "FY", "B"):
                zeilen.extend(nach_typ.get(typ, []))
    _nettogewinn_ohne_minderheiten(zeilen)
    zeilen.sort(key=lambda z: (z["kennzahl"], z["end"], z["typ"]))
    enden_alle = [z["end"] for z in zeilen]
    meta = {
        "cik": cik, "name": firma.get("entityName"),
        "filer_typ": filer_typ(firma),
        "waehrungen_umsatz": sorted(waehrungen),
        "erstes_ende": min(enden_alle) if enden_alle else None,
        "letztes_ende": max(enden_alle) if enden_alle else None,
        "zeilen": len(zeilen),
        "einreichungen": len(enden),
    }
    return meta, zeilen


def quartalsreihe(zeilen, kennzahl, fassung="erst"):
    """Bequemer Blick: [(end, wert, quelle), ...] der Quartale einer
    Kennzahl, chronologisch.

    STANDARD IST DIE ERSTFASSUNG (Gerhards Entscheid F11 vom 02.09.2026,
    abweichend von meiner Empfehlung): "Fuer mich zaehlt, was damals
    bekannt war, nicht was die Firma zwei Jahre spaeter daraus gemacht
    hat." Die Letztfassung bleibt in jeder Zeile mitgefuehrt und wird auf
    Abruf gezeigt; Abweichungen zwischen beiden nennt die Abfrageschicht
    ausdruecklich. Ebenso F13: Standardachse der Abfrage ist das
    KALENDERQUARTAL (Feld kalender), das Fiskalquartal wird immer mit
    angezeigt."""
    feld = "wert_" + fassung
    return [(z["end"], z[feld], z["quelle"]) for z in zeilen
            if z["kennzahl"] == kennzahl and z["typ"] == "Q"]


# ---------------------------------------------------------------------------
# Selbsttest (ohne Netz): eine synthetische Firma mit allen vier Fallen
# ---------------------------------------------------------------------------

def _fakt(start, end, val, accn, fy, fp, form, filed, frame=None):
    e = {"end": end, "val": val, "accn": accn, "fy": fy, "fp": fp,
         "form": form, "filed": filed}
    if start:
        e["start"] = start
    if frame:
        e["frame"] = frame
    return e


def _synthetische_firma():
    """Geschaeftsjahr = Kalenderjahr. 2023 noch mit SalesRevenueNet, ab
    2024 mit RevenueFromContractWithCustomerExcludingAssessedTax; jede
    Einreichung wiederholt die Vorjahresperiode; der 10-K 2024 traegt nur
    den Jahreswert; Q1 2024 wird im 10-Q Q1 2025 restated."""
    q1_24 = ("2024-01-01", "2024-03-31")
    q2_24 = ("2024-04-01", "2024-06-30")
    q3_24 = ("2024-07-01", "2024-09-30")
    h1_24 = ("2024-01-01", "2024-06-30")
    m9_24 = ("2024-01-01", "2024-09-30")
    fy_24 = ("2024-01-01", "2024-12-31")
    q1_25 = ("2025-01-01", "2025-03-31")
    a = {"q1_24": "0001-24-000001", "q2_24": "0001-24-000002",
         "q3_24": "0001-24-000003", "k_24": "0001-25-000001",
         "q1_25": "0001-25-000002", "k_23": "0001-24-000000"}
    umsatz_neu = [
        _fakt(*q1_24, 100, a["q1_24"], 2024, "Q1", "10-Q", "2024-05-01", "CY2024Q1"),
        _fakt(*q2_24, 200, a["q2_24"], 2024, "Q2", "10-Q", "2024-08-01", "CY2024Q2"),
        _fakt(*h1_24, 300, a["q2_24"], 2024, "Q2", "10-Q", "2024-08-01"),
        _fakt(*q3_24, 300, a["q3_24"], 2024, "Q3", "10-Q", "2024-11-01", "CY2024Q3"),
        _fakt(*m9_24, 600, a["q3_24"], 2024, "Q3", "10-Q", "2024-11-01"),
        _fakt(*fy_24, 1000, a["k_24"], 2024, "FY", "10-K", "2025-02-15", "CY2024"),
        # Vergleichswert Q1 2024 im 10-Q Q1 2025, restated auf 101
        _fakt(*q1_24, 101, a["q1_25"], 2025, "Q1", "10-Q", "2025-05-01"),
        _fakt(*q1_25, 150, a["q1_25"], 2025, "Q1", "10-Q", "2025-05-01", "CY2025Q1"),
    ]
    umsatz_alt = [
        _fakt("2023-01-01", "2023-12-31", 800, a["k_23"], 2023, "FY", "10-K", "2024-02-15", "CY2023"),
        # der 10-K 2024 wiederholt das Vorjahr unter dem NEUEN Konzept nicht,
        # aber unter dem alten steht es nochmals (Vergleich)
        _fakt("2023-01-01", "2023-12-31", 800, a["k_24"], 2024, "FY", "10-K", "2025-02-15"),
        _fakt("2023-10-01", "2023-12-31", 220, a["k_23"], 2023, "FY", "10-K", "2024-02-15", "CY2023Q4"),
    ]
    eps = [
        _fakt(*q1_24, 0.5, a["q1_24"], 2024, "Q1", "10-Q", "2024-05-01"),
        _fakt(*q2_24, 0.6, a["q2_24"], 2024, "Q2", "10-Q", "2024-08-01"),
        _fakt(*q3_24, 0.7, a["q3_24"], 2024, "Q3", "10-Q", "2024-11-01"),
        _fakt(*fy_24, 2.5, a["k_24"], 2024, "FY", "10-K", "2025-02-15"),
    ]
    assets = [
        _fakt(None, "2024-03-31", 5000, a["q1_24"], 2024, "Q1", "10-Q", "2024-05-01", "CY2024Q1I"),
        _fakt(None, "2024-12-31", 5500, a["k_24"], 2024, "FY", "10-K", "2025-02-15", "CY2024Q4I"),
        _fakt(None, "2023-12-31", 4800, a["k_24"], 2024, "FY", "10-K", "2025-02-15"),
        _fakt(None, "2023-12-31", 4800, a["k_23"], 2023, "FY", "10-K", "2024-02-15", "CY2023Q4I"),
    ]
    return {
        "cik": 1, "entityName": "Synthetik Inc.",
        "facts": {
            # Deckblatt-Aktienzahl traegt das Datum kurz vor der Einreichung,
            # NICHT das Periodenende (die Apple-Falle)
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
                _fakt(None, "2025-02-10", 1000000, a["k_24"], 2024, "FY", "10-K", "2025-02-15")]}}},
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": umsatz_neu}},
                "SalesRevenueNet": {"units": {"USD": umsatz_alt}},
                "EarningsPerShareDiluted": {"units": {"USD/shares": eps}},
                "Assets": {"units": {"USD": assets}},
            },
        },
    }


def _ifrs_firma():
    return {
        "cik": 2, "entityName": "Ausland plc",
        "facts": {"ifrs-full": {
            "Revenue": {"units": {"EUR": [
                _fakt("2024-01-01", "2024-12-31", 900, "0002-25-000001", 2024, "FY", "20-F", "2025-03-30")]}},
            "ProfitLoss": {"units": {"EUR": [
                _fakt("2024-01-01", "2024-12-31", 90, "0002-25-000001", 2024, "FY", "20-F", "2025-03-30")]}},
        }},
    }


def _konzern_firma():
    """Nur ProfitLoss (samt Minderheiten) und der Minderheitenanteil
    getaggt, kein NetIncomeLoss."""
    q = ("2025-04-01", "2025-06-30")
    return {
        "cik": 3, "entityName": "Konzern Inc.",
        "facts": {"us-gaap": {
            "ProfitLoss": {"units": {"USD": [
                _fakt(*q, 150, "0003-25-000001", 2025, "Q2", "10-Q", "2025-08-01")]}},
            "NetIncomeLossAttributableToNoncontrollingInterest": {"units": {"USD": [
                _fakt(*q, 10, "0003-25-000001", 2025, "Q2", "10-Q", "2025-08-01")]}},
            "Assets": {"units": {"USD": [
                _fakt(None, "2025-06-30", 900, "0003-25-000001", 2025, "Q2", "10-Q", "2025-08-01")]}},
        }},
    }


def selbsttest() -> int:
    fehler = []

    def p(name, bedingung, zusatz=""):
        print(f"  {'ok  ' if bedingung else 'FEHL'} {name}"
              + (f", {zusatz}" if zusatz else ""))
        if not bedingung:
            fehler.append(name)

    print("Fundament-Normalisierung, Selbsttest (ohne Netz)")
    meta, zeilen = normalisiere(_synthetische_firma())
    p("Inlaendischer US-GAAP-Filer erkannt", meta["filer_typ"] == "inland_usgaap", meta["filer_typ"])

    q = {z["end"]: z for z in zeilen if z["kennzahl"] == "umsatz" and z["typ"] == "Q"}
    p("Vier Quartale 2024 plus Q1 2025 plus Q4 2023",
      sorted(q) == ["2023-12-31", "2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"],
      sorted(q))
    z = q.get("2024-03-31", {})
    p("Q1 2024: Erstfassung 100, Letztfassung 101, restated",
      z.get("wert_erst") == 100 and z.get("wert_letzt") == 101 and z.get("restated") is True,
      f"{z.get('wert_erst')}/{z.get('wert_letzt')}")
    p("Q1 2024: Fiskalperiode aus der Erst-Einreichung (2024 Q1), nicht aus dem Vergleich (2025)",
      z.get("fiskaljahr") == 2024 and z.get("fiskalperiode") == "Q1",
      f"{z.get('fiskaljahr')} {z.get('fiskalperiode')}")
    p("Q1 2024: Erstfassung nennt Formular und Datum",
      z.get("form_erst") == "10-Q" and z.get("filed_erst") == "2024-05-01"
      and z.get("filed_letzt") == "2025-05-01")
    z4 = q.get("2024-12-31", {})
    p("Q4 2024 BERECHNET als Jahr minus Neunmonate (1000 minus 600)",
      z4.get("wert_erst") == 400 and z4.get("quelle") == "berechnet"
      and z4.get("fiskalperiode") == "Q4", f"{z4.get('wert_erst')} {z4.get('quelle')}")
    p("Q4 2024: Kalender CY2024Q4 berechnet",
      z4.get("kalender") == "CY2024Q4" and z4.get("kalender_quelle") == "berechnet")
    p("Q2 2024 amtlich (nicht aus H1 abgeleitet, weil vorhanden)",
      q.get("2024-06-30", {}).get("quelle") == "amtlich"
      and q["2024-06-30"]["wert_erst"] == 200)
    p("Q4 2023 aus dem ALTEN Konzept SalesRevenueNet (Kaskade je Periode)",
      q.get("2023-12-31", {}).get("tag") == "SalesRevenueNet"
      and q["2023-12-31"]["wert_erst"] == 220, q.get("2023-12-31", {}).get("tag"))
    p("Q4 2023: Fiskalperiode Q4 aus dem 10-K (Hauptperiode, fp FY wird Q4)",
      q.get("2023-12-31", {}).get("fiskalperiode") == "Q4")
    p("SEC-Frame uebernommen, wo vorhanden",
      q.get("2024-06-30", {}).get("kalender") == "CY2024Q2"
      and q["2024-06-30"]["kalender_quelle"] == "sec_frame")

    fy = {z["end"]: z for z in zeilen if z["kennzahl"] == "umsatz" and z["typ"] == "FY"}
    p("Jahreswerte 2023 (alt) und 2024 (neu)",
      sorted(fy) == ["2023-12-31", "2024-12-31"] and fy["2023-12-31"]["wert_erst"] == 800
      and fy["2024-12-31"]["wert_erst"] == 1000)
    p("Jahr 2023: zwei Einreichungen zusammengefuehrt, nicht restated",
      fy["2023-12-31"]["n_einreichungen"] == 2 and fy["2023-12-31"]["restated"] is False)
    p("Kein Halbjahres- oder Neunmonatswert in der Ausgabe",
      all(z["typ"] in ("Q", "FY", "B") for z in zeilen))

    eps = {z["end"]: z for z in zeilen if z["kennzahl"] == "eps_verwaessert" and z["typ"] == "Q"}
    p("EPS: KEIN berechnetes Q4 (nicht additiv)",
      "2024-12-31" not in eps and len(eps) == 3, sorted(eps))

    b = {z["end"]: z for z in zeilen if z["kennzahl"] == "bilanzsumme"}
    p("Bilanzsumme: drei Stichtage, Vergleichsbilanz zusammengefuehrt",
      sorted(b) == ["2023-12-31", "2024-03-31", "2024-12-31"]
      and b["2023-12-31"]["n_einreichungen"] == 2)
    p("Bilanzsumme 31.12.2023: Fiskalperiode aus dem 10-K 2023 (Hauptperiode)",
      b["2023-12-31"]["fiskaljahr"] == 2023 and b["2023-12-31"]["fiskalperiode"] == "FY",
      f"{b['2023-12-31']['fiskaljahr']} {b['2023-12-31']['fiskalperiode']}")
    p("Bestands-Kalender als Instant-Frame",
      b["2024-03-31"]["kalender"] == "CY2024Q1I")
    p("Bilanzsumme 31.12.2024: Fiskal 2024 FY trotz spaeterem Deckblatt-Datum (Hauptperiode = haeufigstes Ende)",
      b["2024-12-31"]["fiskaljahr"] == 2024 and b["2024-12-31"]["fiskalperiode"] == "FY",
      f"{b['2024-12-31']['fiskaljahr']} {b['2024-12-31']['fiskalperiode']}")
    p("Q1 2025: Fiskal 2025 Q1 direkt aus der Hauptperiode des 10-Q",
      q["2025-03-31"]["fiskaljahr"] == 2025 and q["2025-03-31"]["fiskalperiode"] == "Q1")

    meta3, zeilen3 = normalisiere(_konzern_firma())
    ng = [z for z in zeilen3 if z["kennzahl"] == "nettogewinn"]
    p("Konzern ohne NetIncomeLoss: Aktionaersanteil = ProfitLoss minus Minderheiten (150 minus 10), berechnet",
      len(ng) == 1 and ng[0]["wert_erst"] == 140 and ng[0]["quelle"] == "berechnet"
      and ng[0]["fiskaljahr"] == 2025 and ng[0]["fiskalperiode"] == "Q2",
      ng[0] if ng else "keine Zeile")
    p("Minderheiten-Ergebnis als eigene Kennzahl",
      any(z["kennzahl"] == "minderheiten_ergebnis" and z["wert_erst"] == 10 for z in zeilen3))

    archiv_firma = dict(_synthetische_firma(), cik="0000000001")
    meta4, zeilen4 = normalisiere(archiv_firma)
    p("CIK aus dem Bulk-Archiv ('0000000001') wird zur Zahl 1, in Metadaten, Zeilen und Rohdaten",
      meta4["cik"] == 1 and all(z["cik"] == 1 for z in zeilen4)
      and all(f["cik"] == 1 for f in alle_fakten(archiv_firma)))
    bank = {"cik": 4, "entityName": "Bank Corp.", "facts": {"us-gaap": {
        "InterestIncomeExpenseNet": {"units": {"USD": [
            _fakt("2025-04-01", "2025-06-30", 500, "0004-25-000001", 2025, "Q2", "10-Q", "2025-08-01")]}},
        "ProvisionForLoanLeaseAndOtherLosses": {"units": {"USD": [
            _fakt("2025-04-01", "2025-06-30", 40, "0004-25-000001", 2025, "Q2", "10-Q", "2025-08-01")]}},
        "Deposits": {"units": {"USD": [
            _fakt(None, "2025-06-30", 9000, "0004-25-000001", 2025, "Q2", "10-Q", "2025-08-01")]}},
        "CommonEquityTierOneCapitalToRiskWeightedAssets": {"units": {"pure": [
            _fakt(None, "2025-06-30", 0.15, "0004-25-000001", 2025, "Q2", "10-Q", "2025-08-01")]}},
    }}}
    _, zb = normalisiere(bank)
    werte = {z["kennzahl"]: (z["wert_erst"], z["einheit"]) for z in zb}
    p("Sonderbranchen (F14): Zinsueberschuss, Risikovorsorge, Einlagen und Kernkapitalquote einer Bank",
      werte.get("zinsueberschuss") == (500, "USD") and werte.get("risikovorsorge") == (40, "USD")
      and werte.get("einlagen") == (9000, "USD") and werte.get("kernkapitalquote") == (0.15, "pure"),
      werte)
    p("Sonderbranchen: 40 Kernzeilen plus 17 Branchenzeilen im Register",
      len(KENNZAHLEN) == 57, len(KENNZAHLEN))

    ao = [z for z in zeilen if z["kennzahl"] == "aktien_ausstehend"]
    p("Deckblatt-Aktienzahl aus der dei-Taxonomie",
      len(ao) == 1 and ao[0]["taxonomie"] == "dei" and ao[0]["wert_erst"] == 1000000)

    roh = list(alle_fakten(_synthetische_firma()))
    p("Rohdaten: jeder Fakt einmal (F2)", len(roh) == 8 + 3 + 4 + 4 + 1, len(roh))

    meta2, zeilen2 = normalisiere(_ifrs_firma())
    p("IFRS-Filer erkannt und Umsatz aus ifrs-full in EUR ausgewiesen",
      meta2["filer_typ"] == "ausland_ifrs" and meta2["waehrungen_umsatz"] == ["EUR"]
      and any(z["kennzahl"] == "umsatz" and z["einheit"] == "EUR" and z["taxonomie"] == "ifrs-full"
              for z in zeilen2), meta2)
    p("Kalenderrahmen: 2. August liegt naeher am 30. Juni als am 30. September",
      kalender_rahmen(dt.date(2025, 8, 2), "Q") == "CY2025Q2")
    p("Kalenderrahmen: Geschaeftsjahr mit Ende 27.09. wird CY2025Q3FY",
      kalender_rahmen(dt.date(2025, 9, 27), "FY") == "CY2025Q3FY")
    p("Periodentyp: 13 Wochen sind ein Quartal, 52 Wochen ein Jahr",
      _periodentyp(dt.date(2025, 5, 4), dt.date(2025, 8, 2)) == "Q"
      and _periodentyp(dt.date(2024, 9, 29), dt.date(2025, 9, 27)) == "FY")

    if fehler:
        print(f"\n{len(fehler)} FEHLER: {', '.join(fehler)}")
        return 1
    print("\nAlles bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(selbsttest())
