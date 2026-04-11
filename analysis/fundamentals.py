import pandas as pd

def calculate_cagr(series):
    series = series.dropna()
    if len(series) < 2:
        return None

    start = series.iloc[-1]
    end = series.iloc[0]
    years = len(series) - 1

    if start <= 0:
        return None

    return (end / start) ** (1 / years) - 1


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

    # Balance Sheet
    if not balance.empty:
        debt = balance.loc["Total Debt"].iloc[0] if "Total Debt" in balance.index else None
        equity = balance.loc["Total Stockholder Equity"].iloc[0] if "Total Stockholder Equity" in balance.index else None

        result["debt"] = debt
        result["equity"] = equity

        if debt and equity and equity != 0:
            result["debt_to_equity"] = debt / equity

    # Cash Flow
    if not cashflow.empty:
        op_cf = cashflow.loc["Total Cash From Operating Activities"].iloc[0] if "Total Cash From Operating Activities" in cashflow.index else None
        capex = cashflow.loc["Capital Expenditures"].iloc[0] if "Capital Expenditures" in cashflow.index else None

        result["operating_cashflow"] = op_cf
        result["capex"] = capex

        if op_cf and capex:
            result["free_cashflow"] = op_cf + capex

    return result