import yfinance as yf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import re
from utils.formatters import calculate_cagr
from services.yf_bootstrap import configure_yfinance_cache


configure_yfinance_cache()


def clean_years(df):
    df.columns = [str(col.year) for col in df.columns]
    return df


# ================================
# NSE Data (Priority 1 for India)
# ================================
def fetch_nse_data(symbol, session=None):
    try:
        if session is None:
            session = requests.Session()
            session.trust_env = False
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.nseindia.com/",
            })
            session.get("https://www.nseindia.com", timeout=10)

        url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        res = session.get(url, timeout=10)
        if res.status_code != 200:
            return {}

        data = res.json()
        result = {}

        metrics = data.get("financialData", {})
        if metrics:
            roe = metrics.get("roe")
            roce = metrics.get("roce")
            if roe:
                result["ROE"] = round(float(roe), 2)
            if roce:
                result["ROCE"] = round(float(roce), 2)

        return result
    except:
        return {}


# ================================
# Screener Data (Priority 2 for India)
# ================================
def fetch_screener_data(ticker):
    if not ticker.endswith(".NS"):
        return {}

    symbol = ticker.replace(".NS", "").upper()
    url = f"https://www.screener.in/company/{symbol}/"
    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    session.trust_env = False

    try:
        response = session.get(url, headers=headers, timeout=10)
    except:
        return {}

    if response.status_code != 200:
        return {}

    soup = BeautifulSoup(response.text, "lxml")
    data = {}

    # Try structured ratio list first
    for li in soup.select("ul.company-ratios li"):
        name_tag = li.select_one(".name")
        value_tag = li.select_one(".value, .nowrap")
        if not name_tag or not value_tag:
            continue

        name = name_tag.get_text(strip=True)
        value_text = value_tag.get_text(strip=True).replace(",", "").replace("%", "").strip()

        try:
            value = float(value_text)
        except:
            value = value_text

        if "ROE" in name:
            data["ROE"] = round(value, 2) if isinstance(value, float) else None
        elif "ROCE" in name:
            data["ROCE"] = round(value, 2) if isinstance(value, float) else None
        elif "Debt to equity" in name or "Debt / Equity" in name:
            data["Debt-Equity (Screener)"] = value
        elif "Interest Coverage" in name:
            data["Interest Coverage"] = value
        elif "Promoter holding" in name:
            data["Promoter Holding"] = value_text

    # Fallback: old text parsing if structured failed
    if "ROE" not in data:
        for li in soup.find_all("li"):
            text = li.get_text(strip=True)
            if "ROE" in text and "ROE" not in data:
                try:
                    match = re.search(r"(\d+\.?\d*)\s*%", text)
                    if match:
                        data["ROE"] = round(float(match.group(1)), 2)
                except:
                    pass
            elif "ROCE" in text and "ROCE" not in data:
                try:
                    match = re.search(r"(\d+\.?\d*)\s*%", text)
                    if match:
                        data["ROCE"] = round(float(match.group(1)), 2)
                except:
                    pass
            elif "Interest Coverage" in text and "Interest Coverage" not in data:
                val = text.split()[-1]
                try:
                    data["Interest Coverage"] = round(float(val), 2)
                except:
                    data["Interest Coverage"] = val
            elif "Promoter holding" in text and "Promoter Holding" not in data:
                data["Promoter Holding"] = text.split()[-1]

    return data


# ================================
# Relative Strength
# ================================
def relative_strength(stock_hist):
    try:
        # Use Ticker object for better reliability with Indian indices
        nifty_tk = yf.Ticker("^NSEI")
        nifty = nifty_tk.history(period="6mo")
        if nifty is None or nifty.empty:
            return None
        stock_return = stock_hist["Close"].iloc[-1] / stock_hist["Close"].iloc[0] - 1
        nifty_return = nifty["Close"].iloc[-1] / nifty["Close"].iloc[0] - 1
        return "Outperforming NIFTY" if stock_return > nifty_return else "Underperforming NIFTY"
    except Exception:
        return None


# ================================
# MAIN OLD ENGINE LOGIC
# ================================
def _idx(df, name):
    """Case-insensitive index lookup. Returns None if not found."""
    if df is None or df.empty:
        return None
    for col in df.index:
        if col.lower() == name.lower():
            return col
    return None

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

    # Helper: case-insensitive loc
    def _get(df, name):
        k = _idx(df, name)
        if k is None:
            return None
        return df.loc[k]

    # ================= QUALITY =================
    rev_key = _idx(income, "Total Revenue")
    ni_key = _idx(income, "Net Income")
    ebit_key = _idx(income, "EBIT")

    if rev_key:
        revenue = income.loc[rev_key]
        rev_cagr = calculate_cagr(revenue)
        ratios["Revenue CAGR"] = round(rev_cagr * 100, 2) if rev_cagr else None

    if ni_key:
        profit = income.loc[ni_key]
        profit_cagr = calculate_cagr(profit)
        ratios["Profit CAGR"] = round(profit_cagr * 100, 2) if profit_cagr else None

    if ebit_key and rev_key:
        try:
            ebit_val = income.loc[ebit_key].iloc[0]
            rev_val = income.loc[rev_key].iloc[0]
            if rev_val and rev_val != 0:
                ratios["Operating Margin"] = round((ebit_val / rev_val) * 100, 2)
        except:
            pass

    # Net Margin = Net Income / Total Revenue
    if ni_key and rev_key:
        try:
            ni_val = income.loc[ni_key].iloc[0]
            rev_val = income.loc[rev_key].iloc[0]
            if rev_val and rev_val != 0:
                ratios["Net Margin"] = round((ni_val / rev_val) * 100, 2)
        except:
            pass

    # ================= SAFETY =================
    debt_key = _idx(balance, "Total Debt")
    equity_key = _idx(balance, "Stockholders Equity")
    if debt_key and equity_key:
        debt_val = balance.loc[debt_key].iloc[0]
        equity_val = balance.loc[equity_key].iloc[0]
        if equity_val:
            ratios["Debt-Equity"] = round(debt_val / equity_val, 2)

    int_exp_key = _idx(income, "Interest Expense")
    if ebit_key and int_exp_key:
        ebit_val = income.loc[ebit_key].iloc[0]
        interest_val = abs(income.loc[int_exp_key].iloc[0])
        if interest_val:
            ratios["Interest Coverage"] = round(ebit_val / interest_val, 2)

    # ================= CFO / PAT =================
    ocf_key = _idx(cashflow, "Operating Cash Flow")
    capex_key = _idx(cashflow, "Capital Expenditure")

    if ocf_key and ni_key:
        try:
            op_cf_val = cashflow.loc[ocf_key].iloc[0]
            ni_val = income.loc[ni_key].iloc[0]
            if ni_val and ni_val != 0:
                ratios["CFO/PAT"] = round(op_cf_val / ni_val, 2)
        except:
            pass

    # FCF Yield = Free Cash Flow / Market Cap
    if ocf_key and capex_key:
        try:
            op_cf_val = cashflow.loc[ocf_key].iloc[0]
            capex_val = cashflow.loc[capex_key].iloc[0]
            fcf_val = op_cf_val + capex_val
            market_cap = info_data.get("marketCap")
            if market_cap and market_cap != 0:
                ratios["FCF Yield"] = round((fcf_val / market_cap) * 100, 2)
        except:
            pass

    # ================= VALUATION =================
    ratios["P/E"] = info_data.get("trailingPE")
    ratios["P/B"] = info_data.get("priceToBook")
    ratios["EV/EBITDA"] = info_data.get("enterpriseToEbitda")

    # EPS TTM = Net Income / Shares Outstanding
    shares_out = info_data.get("sharesOutstanding") or info_data.get("impliedSharesOutstanding")
    if ni_key and shares_out:
        try:
            ni_val = income.loc[ni_key].iloc[0]
            if ni_val and shares_out:
                ratios["EPS TTM"] = round(ni_val / shares_out, 2)
        except:
            pass

    # Book Value = Stockholders Equity / Shares Outstanding
    if equity_key and shares_out:
        try:
            eq_val = balance.loc[equity_key].iloc[0]
            if eq_val and shares_out:
                ratios["Book Value"] = round(eq_val / shares_out, 2)
        except:
            pass

    # Dividend Yield
    dy = info_data.get("dividendYield")
    if dy:
        # yfinance dividendYield is already a percentage (e.g. 0.41 for 0.41%)
        # but may sometimes be a decimal; check via magnitude
        if dy > 0.1:
            ratios["Dividend Yield"] = round(dy, 2)
        else:
            ratios["Dividend Yield"] = round(dy * 100, 2)
    else:
        # Try computing: Dividends Paid / Market Cap
        div_key = _idx(cashflow, "Cash Dividends Paid") or _idx(cashflow, "Dividends Paid") or _idx(cashflow, "Common Stock Dividend Paid")
        if div_key:
            try:
                div_paid = abs(cashflow.loc[div_key].iloc[0])
                market_cap = info_data.get("marketCap")
                if div_paid and market_cap and market_cap != 0:
                    ratios["Dividend Yield"] = round((div_paid / market_cap) * 100, 2)
            except:
                pass

    # FII Holding from yfinance
    fii_holding = info_data.get("heldPercentInstitutions")
    if fii_holding:
        ratios["FII Holding"] = round(fii_holding * 100, 2)

    # Promoter Holding fallback from yfinance
    promoter_holding = info_data.get("heldPercentInsiders")
    if promoter_holding and "Promoter Holding" not in ratios:
        ratios["Promoter Holding"] = round(promoter_holding * 100, 2)

    # ================= MARKET =================
    hist = stock_data["history"]
    if not hist.empty:
        try:
            ema55 = hist["Close"].ewm(span=55).mean()
            ema55_slope = ema55.iloc[-1] - ema55.iloc[-5]
            ratios["Trend"] = "Uptrend" if ema55_slope > 0 else "Downtrend"
        except:
            ratios["Trend"] = "N/A"

        vol = hist["Close"].pct_change().std() * np.sqrt(252) * 100
        ratios["Volatility"] = round(vol, 2)

        rs = relative_strength(hist)
        if rs:
            ratios["Relative Strength"] = rs

    assets_key = _idx(balance, "Total Assets")
    cl_key = _idx(balance, "Current Liabilities")

    # ================= ROE / ROCE PRIORITY =================
    if ticker.endswith(".NS") or ticker.endswith(".BO"):
        symbol = ticker.replace(".NS", "").replace(".BO", "").upper()

        # Priority 1: NSE
        nse_data = fetch_nse_data(symbol)
        if nse_data.get("ROE"):
            ratios["ROE"] = nse_data["ROE"]
        if nse_data.get("ROCE"):
            ratios["ROCE"] = nse_data["ROCE"]

        # Priority 2: Screener (always fetch for Promoter Holding + fallback ROE/ROCE)
        screener_data = fetch_screener_data(ticker)
        if "ROE" not in ratios and screener_data.get("ROE"):
            ratios["ROE"] = screener_data["ROE"]
        if "ROCE" not in ratios and screener_data.get("ROCE"):
            ratios["ROCE"] = screener_data["ROCE"]
        if screener_data.get("Interest Coverage") and "Interest Coverage" not in ratios:
            ratios["Interest Coverage"] = screener_data["Interest Coverage"]
        if screener_data.get("Promoter Holding"):
            ratios["Promoter Holding"] = screener_data["Promoter Holding"]

        # Priority 3: yfinance fallback
        if "ROE" not in ratios:
            roe_yf = info_data.get("returnOnEquity")
            if roe_yf:
                ratios["ROE"] = round(roe_yf * 100, 2)

        # Priority 3b: Computed ROCE from financial statements
        if "ROCE" not in ratios and ebit_key and assets_key:
            try:
                ebit_val = income.loc[ebit_key].iloc[0]
                total_assets_val = balance.loc[assets_key].iloc[0]
                if ebit_val and total_assets_val:
                    if cl_key and total_assets_val != balance.loc[cl_key].iloc[0]:
                        capital_employed = total_assets_val - balance.loc[cl_key].iloc[0]
                        if capital_employed > 0:
                            ratios["ROCE"] = round((ebit_val / capital_employed) * 100, 2)
                    elif total_assets_val > 0:
                        ratios["ROCE"] = round((ebit_val / total_assets_val) * 100, 2)
            except:
                pass

        # Priority 3c: yfinance returnOnAssets as last resort
        if "ROCE" not in ratios:
            roce_yf = info_data.get("returnOnAssets")
            if roce_yf:
                ratios["ROCE"] = round(roce_yf * 100, 2)

    else:
        # US stocks — yfinance only
        roe_yf = info_data.get("returnOnEquity")
        if roe_yf:
            ratios["ROE"] = round(roe_yf * 100, 2)

    # Computed ROE fallback for ALL stocks (not just Indian)

    # ================= COMPUTED ROE FALLBACK =================
    if "ROE" not in ratios:
        try:
            if ni_key and equity_key:
                ni_val = income.loc[ni_key].iloc[0]
                eq_val = balance.loc[equity_key].iloc[0]
                if eq_val and eq_val != 0:
                    ratios["ROE"] = round((ni_val / eq_val) * 100, 2)
        except:
            pass

    # ================= PIOTROSKI SCORE =================
    try:
        score = 0

        # F1: Positive Net Income (latest year)
        if ni_key:
            ni_series = income.loc[ni_key].dropna()
            if len(ni_series) >= 1 and ni_series.iloc[0] > 0:
                score += 1

        # F2: Positive Operating Cash Flow (latest year)
        if ocf_key:
            ocf_series = cashflow.loc[ocf_key].dropna()
            if len(ocf_series) >= 1 and ocf_series.iloc[0] > 0:
                score += 1

        # F3: ROE increasing (YoY)
        if ni_key and equity_key:
            ni_series = income.loc[ni_key].dropna()
            eq_series = balance.loc[equity_key].dropna()
            if len(ni_series) >= 2 and len(eq_series) >= 2:
                roe_t0 = ni_series.iloc[0] / eq_series.iloc[0] if eq_series.iloc[0] != 0 else 0
                roe_t1 = ni_series.iloc[1] / eq_series.iloc[1] if eq_series.iloc[1] != 0 else 0
                if roe_t0 > roe_t1:
                    score += 1

        # F4: OCF > Net Income (quality of earnings)
        if ocf_key and ni_key:
            ocf_val = cashflow.loc[ocf_key].iloc[0]
            ni_val = income.loc[ni_key].iloc[0]
            if ocf_val and ni_val and ocf_val > ni_val:
                score += 1

        # F5: Decreasing Debt/Equity ratio
        if debt_key and equity_key:
            debt_series = balance.loc[debt_key].dropna()
            eq_series = balance.loc[equity_key].dropna()
            if len(debt_series) >= 2 and len(eq_series) >= 2:
                de_t0 = debt_series.iloc[0] / eq_series.iloc[0] if eq_series.iloc[0] != 0 else float('inf')
                de_t1 = debt_series.iloc[1] / eq_series.iloc[1] if eq_series.iloc[1] != 0 else float('inf')
                if de_t0 < de_t1:
                    score += 1

        # F6: Increasing Current Ratio
        ca_key = _idx(balance, "Current Assets")
        if ca_key and cl_key:
            ca_series = balance.loc[ca_key].dropna()
            cl_series = balance.loc[cl_key].dropna()
            if len(ca_series) >= 2 and len(cl_series) >= 2:
                cr_t0 = ca_series.iloc[0] / cl_series.iloc[0] if cl_series.iloc[0] != 0 else 0
                cr_t1 = ca_series.iloc[1] / cl_series.iloc[1] if cl_series.iloc[1] != 0 else 0
                if cr_t0 > cr_t1:
                    score += 1

        # F7: No new shares issued (shares outstanding not increased)
        shares_out_t0 = info_data.get("sharesOutstanding")
        shares_out_t1 = info_data.get("impliedSharesOutstanding")
        if shares_out_t0 and shares_out_t1:
            if shares_out_t0 <= shares_out_t1 * 1.02:
                score += 1

        if score > 0:
            ratios["Piotroski Score"] = f"{score}/7"
    except:
        pass

    # ================= TABLES =================
    tables = {}

    if not income.empty:
        income_table = income.iloc[:, :5].copy()
        income_table = clean_years(income_table)
        income_table = income_table.map(
            lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x)
        tables["income"] = income_table.to_html(
            classes="table-auto w-full text-sm text-slate-300 border border-slate-700",
            border=0)

    if not cashflow.empty:
        cash_table = cashflow.iloc[:, :5].copy()
        cash_table = clean_years(cash_table)
        cash_table = cash_table.map(
            lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x)
        tables["cash"] = cash_table.to_html(
            classes="table-auto w-full text-sm text-slate-300 border border-slate-700",
            border=0)

    if not balance.empty:
        balance_table = balance.iloc[:, :5].copy()
        balance_table = clean_years(balance_table)
        balance_table = balance_table.map(
            lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x)
        tables["balance"] = balance_table.to_html(
            classes="table-auto w-full text-sm text-slate-300 border border-slate-700",
            border=0)

    result["ratios"] = ratios
    result["tables"] = tables

    return result
