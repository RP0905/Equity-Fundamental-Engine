import yfinance as yf
import pandas as pd

# ==============================
# USER INPUT
# ==============================

ticker = input("Enter ticker (e.g., AAPL or TCS.NS): ").upper()
stock = yf.Ticker(ticker)

# ==============================
# BASIC INFO
# ==============================

info = stock.info

print("\n===== BASIC COMPANY INFO =====")
print("Company Name:", info.get("longName", "N/A"))
print("Sector:", info.get("sector", "N/A"))
print("Industry:", info.get("industry", "N/A"))
print("Country:", info.get("country", "N/A"))

print("\n===== MARKET DATA =====")
print("Market Cap:", info.get("marketCap", "N/A"))
print("PE Ratio:", info.get("trailingPE", "N/A"))
print("Dividend Yield:", info.get("dividendYield", "N/A"))

# ==============================
# FETCH FINANCIAL STATEMENTS
# ==============================

income = stock.financials
cashflow = stock.cashflow
balance = stock.balance_sheet


# ==============================
# FORMAT FUNCTION (₹ CRORES)
# ==============================

def format_indian(value):
    if isinstance(value, (int, float)):
        return f"{value/1e7:.2f} Cr"
    return "N/A"


# ==============================
# INCOME STATEMENT (5 YEARS)
# ==============================

if not income.empty:

    print("\n===== INCOME STATEMENT (Last 5 Years) =====")

    income_rows = [
        row for row in ["Total Revenue", "Net Income", "Ebit"]
        if row in income.index
    ]

    income_table = income.loc[income_rows]
    income_table = income_table.iloc[:, :5]
    income_table = income_table.applymap(format_indian)

    print(income_table)

else:
    print("\nIncome statement not available.")


# ==============================
# CASH FLOW (5 YEARS)
# ==============================

if not cashflow.empty:

    print("\n===== CASH FLOW (Last 5 Years) =====")

    possible_ocf_names = [
        "Total Cash From Operating Activities",
        "Operating Cash Flow"
    ]

    ocf_name = next(
        (name for name in possible_ocf_names if name in cashflow.index),
        None
    )

    rows = []
    if ocf_name:
        rows.append(ocf_name)

    if "Capital Expenditures" in cashflow.index:
        rows.append("Capital Expenditures")

    cash_table = cashflow.loc[rows]
    cash_table = cash_table.iloc[:, :5]
    cash_table = cash_table.applymap(format_indian)

    print(cash_table)

else:
    print("\nCash flow statement not available.")


# ==============================
# BALANCE SHEET (5 YEARS)
# ==============================

if not balance.empty:

    print("\n===== BALANCE SHEET (Last 5 Years) =====")

    balance_rows = [
        row for row in ["Total Stockholder Equity", "Total Debt"]
        if row in balance.index
    ]

    balance_table = balance.loc[balance_rows]
    balance_table = balance_table.iloc[:, :5]
    balance_table = balance_table.applymap(format_indian)

    print(balance_table)

else:
    print("\nBalance sheet not available.")