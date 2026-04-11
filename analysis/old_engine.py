import yfinance as yf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import re


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


def percent(x):
    if x is None:
        return None
    return x


def format_value(value, country):
    if not isinstance(value, (int, float)) or pd.isna(value):
        return None
    return value


def clean_years(df):
    df.columns = [str(col.year) for col in df.columns]
    return df


# ================================
# Screener Data (ROBUST FIX)
# ================================
def fetch_screener_data(ticker):

    if not ticker.endswith(".NS"):
        return {}

    symbol = ticker.replace(".NS", "").upper()
    url = f"https://www.screener.in/company/{symbol}/"

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return {}

    soup = BeautifulSoup(response.text, "lxml")

    data = {}

    for li in soup.find_all("li"):
        text = li.get_text(strip=True)

        # ---------- FIXED ROE ----------
        if "ROE" in text:
            try:
                match = re.search(r"(\d+\.?\d*)", text)
                if match:
                    value = float(match.group(1))
                    data["ROE"] = value / 100
                else:
                    data["ROE"] = None
            except:
                data["ROE"] = None

        # ---------- FIXED ROCE ----------
        elif "ROCE" in text:
            try:
                match = re.search(r"(\d+\.?\d*)", text)
                if match:
                    value = float(match.group(1))
                    data["ROCE"] = value / 100
                else:
                    data["ROCE"] = None
            except:
                data["ROCE"] = None

        elif "Debt to equity" in text:
            data["Debt-Equity (Screener)"] = text.split()[-1]

        elif "Interest Coverage" in text:
            data["Interest Coverage"] = text.split()[-1]

        elif "Promoter holding" in text:
            data["Promoter Holding"] = text.split()[-1]

        elif "FIIs holding" in text or "FII holding" in text:
            data["Institutional Holding"] = text.split()[-1]

    return data


# ================================
# Relative Strength
# ================================
def relative_strength(stock_hist):

    try:
        nifty = yf.download("^NSEI", period="6mo", interval="1d")

        stock_return = stock_hist["Close"].iloc[-1] / stock_hist["Close"].iloc[0] - 1
        nifty_return = nifty["Close"].iloc[-1] / nifty["Close"].iloc[0] - 1

        return "Outperforming NIFTY" if stock_return > nifty_return else "Underperforming NIFTY"

    except:
        return None


# ================================
# MAIN OLD ENGINE LOGIC
# ================================
def get_old_data(stock_data, ticker):

    info_data = stock_data["info"]
    income = stock_data["financials"]
    balance = stock_data["balance_sheet"]
    cashflow = stock_data["cashflow"]

    result = {}

    # ================= INFO =================
    result["company_info"] = {
        "name": info_data.get("longName"),
        "sector": info_data.get("sector"),
        "industry": info_data.get("industry"),
        "country": info_data.get("country"),
        "market_cap": info_data.get("marketCap"),
        "pe": info_data.get("trailingPE"),
        "dividend": info_data.get("dividendYield"),
    }

    ratios = {}

    # ================= QUALITY =================
    if not income.empty:
        if "Total Revenue" in income.index:
            revenue = income.loc["Total Revenue"]
            ratios["Revenue CAGR"] = calculate_cagr(revenue)

        if "Net Income" in income.index:
            profit = income.loc["Net Income"]
            ratios["Profit CAGR"] = calculate_cagr(profit)

        if "Total Revenue" in income.index and "Net Income" in income.index:
            try:
                margin = (income.loc["Net Income"].iloc[0] /
                          income.loc["Total Revenue"].iloc[0]) * 100
                ratios["Operating Margin"] = margin
            except:
                pass

    # ================= SAFETY =================
    if not balance.empty:
        if "Total Debt" in balance.index and "Total Stockholder Equity" in balance.index:
            debt = balance.loc["Total Debt"].iloc[0]
            equity = balance.loc["Total Stockholder Equity"].iloc[0]

            if equity:
                ratios["Debt-Equity"] = debt / equity

    if not income.empty:
        if "Ebit" in income.index and "Interest Expense" in income.index:
            ebit = income.loc["Ebit"].iloc[0]
            interest = abs(income.loc["Interest Expense"].iloc[0])

            if interest:
                ratios["Interest Coverage"] = ebit / interest

    # ================= VALUATION =================
    ratios["P/E"] = info_data.get("trailingPE")
    ratios["P/B"] = info_data.get("priceToBook")
    ratios["EV/EBITDA"] = info_data.get("enterpriseToEbitda")

    # ================= MARKET =================
    hist = stock_data["history"]

    if not hist.empty:
        ratios["Trend"] = "Uptrend" if hist["Close"].iloc[-1] > hist["Close"].mean() else "Downtrend"

        vol = hist["Close"].pct_change().std() * np.sqrt(252) * 100
        ratios["Volatility"] = vol

        rs = relative_strength(hist)
        if rs:
            ratios["Relative Strength"] = rs

    # ================= Screener =================
    ratios.update(fetch_screener_data(ticker))

    result["ratios"] = ratios

    # ================= TABLES =================
    tables = {}

    if not income.empty:
        income_table = income.iloc[:, :5].copy()
        income_table = clean_years(income_table)
        income_table = income_table.applymap(lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x)

        tables["income"] = income_table.to_html(
            classes="table-auto w-full text-sm text-slate-300 border border-slate-700",
            border=0
        )

    if not cashflow.empty:
        cash_table = cashflow.iloc[:, :5].copy()
        cash_table = clean_years(cash_table)
        cash_table = cash_table.applymap(lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x)

        tables["cash"] = cash_table.to_html(
            classes="table-auto w-full text-sm text-slate-300 border border-slate-700",
            border=0
        )

    if not balance.empty:
        balance_table = balance.iloc[:, :5].copy()
        balance_table = clean_years(balance_table)
        balance_table = balance_table.applymap(lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x)

        tables["balance"] = balance_table.to_html(
            classes="table-auto w-full text-sm text-slate-300 border border-slate-700",
            border=0
        )

    result["tables"] = tables

    return result