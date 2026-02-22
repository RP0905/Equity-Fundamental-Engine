from flask import Flask, render_template, request
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

# ======================================================
# BASIC HELPERS
# ======================================================

def calculate_cagr(series):
    series = series.dropna()
    if len(series) < 2:
        return "N/A"

    start = series.iloc[-1]
    end = series.iloc[0]
    years = len(series) - 1

    if start <= 0:
        return "N/A"

    cagr = (end / start) ** (1 / years) - 1
    return f"{cagr*100:.2f}%"


def percent(x):
    if x is None or isinstance(x, str):
        return "N/A"
    return f"{x:.2f}%"


def format_value(value, country):
    if not isinstance(value, (int, float)) or pd.isna(value):
        return "N/A"
    return f"{value/1e7:.2f} Cr" if country == "India" else f"{value/1e9:.2f} B"


def clean_years(df):
    df.columns = [str(col.year) for col in df.columns]
    return df


# ======================================================
# SCREENER.IN DATA (INDIA ONLY) — CLEAN EXTRACTION
# ======================================================

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

        if "ROE" in text:
            data["ROE"] = text.replace("ROE", "").replace(":", "").strip()

        elif "ROCE" in text:
            data["ROCE"] = text.replace("ROCE", "").replace(":", "").strip()

        elif "Debt to equity" in text:
            data["Debt-Equity"] = text.split()[-1]

        elif "Interest Coverage" in text:
            data["Interest Coverage"] = text.split()[-1]

        elif "Promoter holding" in text:
            data["Promoter Holding"] = text.split()[-1]

        elif "FIIs holding" in text or "FII holding" in text:
            data["Institutional Holding"] = text.split()[-1]

    return data


# ======================================================
# RELATIVE STRENGTH vs NIFTY
# ======================================================

def relative_strength(stock_hist):

    try:
        nifty = yf.download("^NSEI", period="6mo", interval="1d")

        stock_return = stock_hist["Close"][-1] / stock_hist["Close"][0] - 1
        nifty_return = nifty["Close"][-1] / nifty["Close"][0] - 1

        return "Outperforming NIFTY" if stock_return > nifty_return else "Underperforming NIFTY"

    except:
        return "N/A"


# ======================================================
# ROUTE
# ======================================================

@app.route("/", methods=["GET", "POST"])
def index():

    info = None
    ratios = None
    tables = None

    if request.method == "POST":

        ticker = request.form["ticker"].upper()
        stock = yf.Ticker(ticker)

        info_data = stock.info
        income = stock.financials
        balance = stock.balance_sheet
        cashflow = stock.cashflow

        country = info_data.get("country", "Unknown")

        # ===============================
        # BASIC INFO
        # ===============================

        info = {
            "name": info_data.get("longName", "N/A"),
            "sector": info_data.get("sector", "N/A"),
            "industry": info_data.get("industry", "N/A"),
            "country": country,
            "market_cap": info_data.get("marketCap", "N/A"),
            "pe": info_data.get("trailingPE", "N/A"),
            "dividend": info_data.get("dividendYield", "N/A"),
        }

        ratios = {}
        tables = {}

        # ==================================================
        # ⭐ CORE QUALITY
        # ==================================================

        revenue_series = income.loc["Total Revenue"] \
            if "Total Revenue" in income.index else None

        profit_series = income.loc["Net Income"] \
            if "Net Income" in income.index else None

        ratios["Revenue CAGR"] = calculate_cagr(revenue_series)
        ratios["Profit CAGR"] = calculate_cagr(profit_series)

        if revenue_series is not None and profit_series is not None:
            try:
                margin = (profit_series.iloc[0] /
                          revenue_series.iloc[0]) * 100
                ratios["Operating Margin"] = percent(margin)
            except:
                ratios["Operating Margin"] = "N/A"

        # ==================================================
        # ⭐ SAFETY
        # ==================================================

        if "Total Debt" in balance.index and \
           "Total Stockholder Equity" in balance.index:

            debt = balance.loc["Total Debt"].iloc[0]
            equity = balance.loc["Total Stockholder Equity"].iloc[0]

            if equity > 0:
                ratios["Debt-Equity"] = f"{debt/equity:.2f}"

        if "Ebit" in income.index and "Interest Expense" in income.index:
            ebit = income.loc["Ebit"].iloc[0]
            interest = abs(income.loc["Interest Expense"].iloc[0])

            if interest > 0:
                ratios["Interest Coverage"] = f"{ebit/interest:.2f}x"

        # ==================================================
        # ⭐ VALUATION
        # ==================================================

        ratios["P/E"] = info_data.get("trailingPE", "N/A")
        ratios["P/B"] = info_data.get("priceToBook", "N/A")
        ratios["EV/EBITDA"] = info_data.get("enterpriseToEbitda", "N/A")

        # ==================================================
        # ⭐ MARKET BEHAVIOR
        # ==================================================

        hist = stock.history(period="6mo")

        if not hist.empty:

            ratios["Trend"] = "Uptrend" if \
                hist["Close"][-1] > hist["Close"].mean() else "Downtrend"

            vol = hist["Close"].pct_change().std() * np.sqrt(252) * 100
            ratios["Volatility"] = f"{vol:.2f}%"

            ratios["Relative Strength"] = relative_strength(hist)

        # ==================================================
        # ⭐ SCREENER DATA (INDIA)
        # ==================================================

        ratios.update(fetch_screener_data(ticker))

        # ==================================================
        # 📊 FINANCIAL TABLES
        # ==================================================

        if not income.empty:

            rows = ["Total Revenue", "Net Income", "Ebit"]
            rows = [r for r in rows if r in income.index]

            income_table = income.loc[rows].iloc[:, :5]
            income_table = clean_years(income_table)

            income_table = income_table.apply(
                lambda col: col.map(lambda x: format_value(x, country))
            )

            tables["income"] = income_table.to_html(classes="data")

        if not cashflow.empty:

            rows = ["Operating Cash Flow", "Capital Expenditures"]
            rows = [r for r in rows if r in cashflow.index]

            cash_table = cashflow.loc[rows].iloc[:, :5]
            cash_table = clean_years(cash_table)

            cash_table = cash_table.apply(
                lambda col: col.map(lambda x: format_value(x, country))
            )

            tables["cash"] = cash_table.to_html(classes="data")

        if not balance.empty:

            rows = ["Total Stockholder Equity", "Total Debt"]
            rows = [r for r in rows if r in balance.index]

            balance_table = balance.loc[rows].iloc[:, :5]
            balance_table = clean_years(balance_table)

            balance_table = balance_table.apply(
                lambda col: col.map(lambda x: format_value(x, country))
            )

            tables["balance"] = balance_table.to_html(classes="data")

    return render_template(
        "index.html",
        info=info,
        ratios=ratios,
        tables=tables
    )


if __name__ == "__main__":
    app.run(debug=True)