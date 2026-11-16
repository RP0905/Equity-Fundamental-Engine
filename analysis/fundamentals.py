import pandas as pd
from utils.formatters import calculate_cagr

def get_fundamentals(data):
    info = data["info"]
    financials = data["financials"]
    balance = data["balance_sheet"]
    cashflow = data["cashflow"]

    result = {}

    # Basic Info
    result["market_cap"] = info.get("marketCap")
    result["pe"] = info.get("trailingPE")
    result["pb"] = info.get("priceToBook")

    # Income Statement
    if not financials.empty:
        if "Total Revenue" in financials.index:
            revenue = financials.loc["Total Revenue"]
            revenue_cagr = calculate_cagr(revenue)
            result["revenue_cagr"] = round(revenue_cagr * 100, 2) if revenue_cagr is not None else None

        if "Net Income" in financials.index:
            profit = financials.loc["Net Income"]
            profit_cagr = calculate_cagr(profit)
            result["profit_cagr"] = round(profit_cagr * 100, 2) if profit_cagr is not None else None

        # Correct Operating Margin (EBIT / Revenue)
        if "Ebit" in financials.index and "Total Revenue" in financials.index:
            try:
                ebit = financials.loc["Ebit"].iloc[0]
                revenue = financials.loc["Total Revenue"].iloc[0]
                if revenue and revenue != 0:
                    result["operating_margin"] = round((ebit / revenue) * 100, 2)
            except:
                pass

    # Balance Sheet
    if not balance.empty:
        debt = balance.loc["Total Debt"].iloc[0] if "Total Debt" in balance.index else None
        equity = balance.loc["Stockholders Equity"].iloc[0] if "Stockholders Equity" in balance.index else None

        result["debt"] = debt
        result["equity"] = equity

        if debt is not None and equity and equity != 0:
            result["debt_to_equity"] = round(debt / equity, 2)

    # Cash Flow
    if not cashflow.empty:
        op_cf = cashflow.loc["Operating Cash Flow"].iloc[0] if "Operating Cash Flow" in cashflow.index else None
        capex = cashflow.loc["Capital Expenditure"].iloc[0] if "Capital Expenditure" in cashflow.index else None

        result["operating_cashflow"] = op_cf
        result["capex"] = capex

        if op_cf is not None and capex is not None:
            result["free_cashflow"] = op_cf + capex

    return result