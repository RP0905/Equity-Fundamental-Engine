import yfinance as yf

from services.yf_bootstrap import configure_yfinance_cache


configure_yfinance_cache()

def get_stock_data(ticker):
    stock = yf.Ticker(ticker)

    return {
        "info": stock.info,
        "financials": stock.financials,
        "balance_sheet": stock.balance_sheet,
        "cashflow": stock.cashflow,
        "history": stock.history(period="1y", interval="1d"),
        "quarterly_financials": stock.quarterly_financials,
        "quarterly_balance": stock.quarterly_balance_sheet,
        "quarterly_cashflow": stock.quarterly_cashflow,
    }
