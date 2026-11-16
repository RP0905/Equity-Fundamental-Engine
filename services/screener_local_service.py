from __future__ import annotations

from datetime import datetime, timezone
import re
import sqlite3

import pandas as pd
import requests
import yfinance as yf

from analysis.technicals import calculate_rsi
from services.local_db import get_db_connection, init_db
from services.nse_universe import get_nse_eq_symbols_ns
from services.screener_parser import fetch_company_html, parse_company_page
from services.yf_bootstrap import configure_yfinance_cache

configure_yfinance_cache()

# init_db() is called lazily inside each function that needs it,
# so we do NOT call it at module-import time (avoids DB-lock
# conflicts when multiple instances share the same cache path).


LOCAL_PARAM_ALIASES = {
    # Basic Valuation
    "market capitalization": ("raw_data", "market_cap"),
    "market cap": ("raw_data", "market_cap"),
    "price to earning": ("raw_data", "pe_ratio"),
    "price to earnings": ("raw_data", "pe_ratio"),
    "p/e": ("raw_data", "pe_ratio"),
    "price to book value": ("raw_data", "pb_ratio"),
    "price to book": ("raw_data", "pb_ratio"),
    "p/b": ("raw_data", "pb_ratio"),
    "dividend yield": ("raw_data", "dividend_yield"),
    "dividend yield percent": ("raw_data", "dividend_yield"),
    
    # Profitability
    "return on equity": ("raw_data", "roe"),
    "roe": ("raw_data", "roe"),
    "return on capital employed": ("raw_data", "roce"),
    "roce": ("raw_data", "roce"),
    "return on assets": ("raw_data", "roa"),
    "roa": ("raw_data", "roa"),
    "net profit margin": ("raw_data", "net_profit_margin"),
    "operating profit margin": ("raw_data", "opm"),
    "gross profit margin": ("raw_data", "gross_margin"),
    "ebitda margin": ("raw_data", "ebitda_margin"),
    
    # Per Share
    "eps": ("raw_data", "eps"),
    "earnings per share": ("raw_data", "eps"),
    "book value per share": ("raw_data", "bvps"),
    "bvps": ("raw_data", "bvps"),
    "dividend per share": ("raw_data", "dps"),
    "dps": ("raw_data", "dps"),
    
    # Leverage & Debt
    "debt": ("raw_data", "borrowings"),
    "total debt": ("raw_data", "borrowings"),
    "debt to equity": ("computed_metrics", "debt_to_equity"),
    "debt/equity": ("computed_metrics", "debt_to_equity"),
    "d/e": ("computed_metrics", "debt_to_equity"),
    "interest coverage ratio": ("computed_metrics", "interest_coverage"),
    "interest coverage": ("computed_metrics", "interest_coverage"),
    "current ratio": ("computed_metrics", "current_ratio"),
    "quick ratio": ("computed_metrics", "quick_ratio"),
    "cash ratio": ("computed_metrics", "cash_ratio"),
    
    # Shareholding
    "promoter holding": ("raw_data", "promoter_holding"),
    "fii holding": ("raw_data", "fii_holding"),
    "dii holding": ("raw_data", "dii_holding"),
    "public holding": ("raw_data", "public_holding"),
    "pledged percentage": ("raw_data", "pledged_percentage"),
    
    # Income Statement
    "sales": ("raw_data", "revenue"),
    "revenue": ("raw_data", "revenue"),
    "profit after tax": ("raw_data", "net_profit"),
    "pat": ("raw_data", "net_profit"),
    "operating profit": ("raw_data", "operating_profit"),
    "ebitda": ("raw_data", "ebitda"),
    "gross profit": ("raw_data", "gross_profit"),
    "profit before tax": ("raw_data", "pbt"),
    "pbt": ("raw_data", "pbt"),
    
    # Quarterly
    "sales latest quarter": ("raw_data", "sales_latest_quarter"),
    "profit after tax latest quarter": ("raw_data", "pat_latest_quarter"),
    "yoy quarterly sales growth": ("raw_data", "qtr_sales_growth_yoy"),
    "yoy quarterly profit growth": ("raw_data", "qtr_profit_growth_yoy"),
    "qoq quarterly sales growth": ("raw_data", "qtr_sales_growth_qoq"),
    "qoq quarterly profit growth": ("raw_data", "qtr_profit_growth_qoq"),
    
    # Growth
    "sales growth": ("raw_data", "sales_growth_3y"),
    "sales growth 3years": ("raw_data", "sales_growth_3y"),
    "sales growth 5years": ("raw_data", "sales_growth_5y"),
    "profit growth": ("raw_data", "profit_growth_3y"),
    "profit growth 3years": ("raw_data", "profit_growth_3y"),
    "profit growth 5years": ("raw_data", "profit_growth_5y"),
    "revenue growth": ("raw_data", "sales_growth_3y"),
    "revenue growth 3years": ("raw_data", "sales_growth_3y"),
    "revenue growth 5years": ("raw_data", "sales_growth_5y"),
    "earnings growth": ("raw_data", "profit_growth_3y"),
    "earnings growth 3years": ("raw_data", "profit_growth_3y"),
    "earnings growth 5years": ("raw_data", "profit_growth_5y"),
    
    # Averages
    "average return on equity 3years": ("raw_data", "avg_roe_3y"),
    "average return on equity 5years": ("raw_data", "avg_roe_5y"),
    "average roe 3years": ("raw_data", "avg_roe_3y"),
    "average roe 5years": ("raw_data", "avg_roe_5y"),
    
    # Price & Technical
    "current price": ("raw_data", "current_price"),
    "price": ("raw_data", "current_price"),
    "52 week high": ("raw_data", "week_high_52"),
    "52 week low": ("raw_data", "week_low_52"),
    "52 week change": ("raw_data", "week_change_52"),
    "volume": ("raw_data", "volume"),
    "average volume": ("raw_data", "avg_volume"),
    "beta": ("raw_data", "beta"),
    "rsi": ("technical_data", "rsi"),
    "macd": ("technical_data", "macd"),
    
    # Cash Flow
    "cash flow from operating": ("raw_data", "cash_flow_operating"),
    "cash flow from investing": ("raw_data", "cash_flow_investing"),
    "cash flow from financing": ("raw_data", "cash_flow_financing"),
    "free cash flow": ("raw_data", "free_cash_flow"),
    "fcf": ("raw_data", "free_cash_flow"),
    "cash and cash equivalents": ("raw_data", "cash"),
    
    # Balance Sheet
    "total assets": ("raw_data", "total_assets"),
    "total liabilities": ("raw_data", "total_liabilities"),
    "shareholders equity": ("raw_data", "equity"),
    "reserves": ("raw_data", "reserves"),
    "inventory": ("raw_data", "inventory"),
    "accounts receivable": ("raw_data", "receivables"),
    "accounts payable": ("raw_data", "payables"),
    
    # Efficiency
    "asset turnover": ("computed_metrics", "asset_turnover"),
    "inventory turnover": ("computed_metrics", "inventory_turnover"),
    "receivables turnover": ("computed_metrics", "receivables_turnover"),
    "working capital": ("computed_metrics", "working_capital"),
    "working capital turnover": ("computed_metrics", "working_capital_turnover"),
    
    # Valuation Multiples
    "earnings yield": ("computed_metrics", "earnings_yield"),
    "price to sales": ("raw_data", "price_to_sales"),
    "p/s": ("raw_data", "price_to_sales"),
    "price to free cash flow": ("raw_data", "price_to_fcf"),
    "p/fcf": ("raw_data", "price_to_fcf"),
    "ev/ebitda": ("raw_data", "ev_ebitda"),
    "enterprise value to ebitda": ("raw_data", "ev_ebitda"),
    "enterprise value": ("raw_data", "enterprise_value"),
    "ev": ("raw_data", "enterprise_value"),
    
    # Dividends
    "payout ratio": ("raw_data", "payout_ratio"),
    "dividend payout ratio": ("raw_data", "payout_ratio"),
    "dividend growth rate": ("raw_data", "dividend_growth"),
}


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_exception(exc):
    return " ".join((str(exc) or exc.__class__.__name__).split())[:200]


def _parse_query_filters(query):
    filters = []
    if not query:
        return filters
    for line in [part.strip() for part in query.splitlines() if part.strip()]:
        for part in [item.strip() for item in re.split(r"\band\b", line, flags=re.IGNORECASE) if item.strip()]:
            lower = part.lower()
            matched = None
            for phrase in sorted(LOCAL_PARAM_ALIASES.keys(), key=len, reverse=True):
                if phrase in lower:
                    matched = phrase
                    break
            if not matched:
                continue
            value_match = None
            operator = None
            for candidate in (">=", "<=", ">", "<", "="):
                if candidate in part:
                    operator = candidate
                    value_match = part.split(candidate, 1)[1].strip()
                    break
            if operator is None:
                continue
            try:
                value = float(value_match.replace(",", "").replace("%", "").strip())
            except Exception:
                continue
            table, column = LOCAL_PARAM_ALIASES[matched]
            filters.append({"table": table, "column": column, "operator": operator, "value": value, "label": matched})
    return filters


def _build_where_clause(filters):
    clauses = []
    params = []
    for item in filters:
        qualified = f"{item['table']}.{item['column']}"
        clauses.append(f"{qualified} IS NOT NULL AND {qualified} {item['operator']} ?")
        params.append(item["value"])
    return clauses, params


def _compute_technical_snapshot(symbol):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1y", interval="1d")
    if hist.empty or len(hist) < 200:
        return None

    close = hist["Close"].astype(float)
    ema_20 = close.ewm(span=20).mean().iloc[-1]
    ema_50 = close.ewm(span=50).mean().iloc[-1]
    ema_200 = close.ewm(span=200).mean().iloc[-1]
    rsi = calculate_rsi(hist).iloc[-1]
    macd_line = close.ewm(span=12).mean() - close.ewm(span=26).mean()

    return {
        "symbol": symbol,
        "timeframe": "daily",
        "price": float(close.iloc[-1]),
        "rsi": float(rsi) if pd.notna(rsi) else None,
        "macd": float(macd_line.iloc[-1]) if pd.notna(macd_line.iloc[-1]) else None,
        "ema_20": float(ema_20),
        "ema_50": float(ema_50),
        "ema_200": float(ema_200),
        "last_updated": utc_now_iso(),
    }


def _upsert(conn, table, data, conflict_column="symbol"):
    columns = list(data.keys())
    placeholders = ", ".join(["?"] * len(columns))
    updates = ", ".join([f"{col}=excluded.{col}" for col in columns if col != conflict_column])
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT({conflict_column}) DO UPDATE SET {updates}"
    )
    conn.execute(sql, [data[col] for col in columns])


def sync_screener_symbol(symbol, include_technicals=True):
    init_db()
    symbol = symbol.replace(".NS", "").replace(".BO", "").upper()

    html, page_url = fetch_company_html(symbol)
    parsed = parse_company_page(html, symbol, page_url=page_url)
    technicals = _compute_technical_snapshot(f"{symbol}.NS") if include_technicals else None

    conn = get_db_connection()
    try:
        _upsert(conn, "stocks", parsed["stock"], conflict_column="symbol")
        _upsert(conn, "raw_data", {"symbol": symbol, **parsed["raw_data"]}, conflict_column="symbol")
        _upsert(conn, "computed_metrics", {"symbol": symbol, **parsed["computed_metrics"]}, conflict_column="symbol")

        conn.execute("DELETE FROM statement_items WHERE symbol = ?", (symbol,))
        for statement_type, rows in parsed["statements"].items():
            period_type = "quarterly" if statement_type == "quarterly_results" else "annual"
            for row in rows:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO statement_items
                    (symbol, statement_type, period_type, period_label, display_order, metric, value, raw_value, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol,
                        statement_type,
                        period_type,
                        row["period_label"],
                        row["display_order"],
                        row["metric"],
                        row["value"],
                        row["raw_value"],
                        utc_now_iso(),
                    ),
                )

        conn.execute("DELETE FROM shareholding_pattern WHERE symbol = ?", (symbol,))
        for period_label, row in parsed["shareholding_pattern"].items():
            conn.execute(
                """
                INSERT OR REPLACE INTO shareholding_pattern
                (symbol, period_label, promoter_holding, fii_holding, dii_holding, public_holding, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    period_label,
                    row.get("promoter_holding"),
                    row.get("fii_holding"),
                    row.get("dii_holding"),
                    row.get("public_holding"),
                    utc_now_iso(),
                ),
            )

        if technicals:
            conn.execute(
                """
                INSERT OR REPLACE INTO technical_data
                (symbol, timeframe, price, rsi, macd, ema_20, ema_50, ema_200, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    technicals["timeframe"],
                    technicals["price"],
                    technicals["rsi"],
                    technicals["macd"],
                    technicals["ema_20"],
                    technicals["ema_50"],
                    technicals["ema_200"],
                    technicals["last_updated"],
                ),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return parsed


def sync_screener_universe(limit=None, include_technicals=False, stop_on_error=False):
    symbols = [symbol.replace(".NS", "") for symbol in get_nse_eq_symbols_ns()]
    if limit is not None:
        symbols = symbols[: int(limit)]

    synced = []
    failures = []
    for symbol in symbols:
        try:
            sync_screener_symbol(symbol, include_technicals=include_technicals)
            synced.append(symbol)
        except Exception as exc:
            message = _clean_exception(exc)
            failures.append({"symbol": symbol, "error": message})
            conn = get_db_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO stocks (symbol, stock_name, last_error, last_synced_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET last_error=excluded.last_error, last_synced_at=excluded.last_synced_at
                    """,
                    (symbol, symbol, message, utc_now_iso()),
                )
                conn.commit()
            finally:
                conn.close()
            if stop_on_error:
                break
    return {"synced": synced, "failures": failures, "requested": len(symbols)}


def get_local_screener_status():
    init_db()
    conn = get_db_connection()
    try:
        stock_count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        raw_count = conn.execute("SELECT COUNT(*) FROM raw_data").fetchone()[0]
        latest = conn.execute("SELECT MAX(last_updated) FROM raw_data").fetchone()[0]
        return {
            "stock_count": stock_count,
            "raw_data_count": raw_count,
            "latest_raw_update": latest,
        }
    finally:
        conn.close()


def run_local_screener(filters):
    init_db()
    query = filters.get("query", "")
    limit_raw = filters.get("limit")
    limit = int(limit_raw) if limit_raw not in (None, "") else None
    parsed_filters = _parse_query_filters(query)
    where_clauses, params = _build_where_clause(parsed_filters)

    sql = """
    SELECT
        stocks.symbol,
        stocks.stock_name AS name,
        raw_data.current_price AS price,
        raw_data.market_cap AS market_cap_cr,
        raw_data.market_cap,
        raw_data.pe_ratio AS pe,
        raw_data.pb_ratio AS pb,
        raw_data.dividend_yield,
        raw_data.roe,
        raw_data.roce,
        raw_data.face_value,
        raw_data.revenue AS sales_cr,
        raw_data.net_profit AS pat_cr,
        raw_data.sales_latest_quarter AS sales_latest_qtr_cr,
        raw_data.pat_latest_quarter AS pat_latest_qtr_cr,
        raw_data.qtr_sales_growth_yoy,
        raw_data.qtr_profit_growth_yoy,
        raw_data.sales_growth_3y,
        raw_data.sales_growth_5y,
        raw_data.profit_growth_3y,
        raw_data.profit_growth_5y,
        raw_data.avg_roe_3y,
        raw_data.avg_roe_5y,
        raw_data.operating_profit AS operating_profit_cr,
        raw_data.total_assets AS total_assets_cr,
        raw_data.total_liabilities AS total_liabilities_cr,
        raw_data.equity AS equity_cr,
        raw_data.reserves AS reserves_cr,
        raw_data.borrowings AS debt_cr,
        raw_data.cash_flow AS cash_flow_cr,
        raw_data.capex AS capex_cr,
        raw_data.promoter_holding,
        raw_data.fii_holding,
        raw_data.dii_holding,
        raw_data.public_holding,
        computed_metrics.earnings_yield,
        computed_metrics.debt_to_equity,
        computed_metrics.current_ratio,
        computed_metrics.interest_coverage,
        computed_metrics.asset_turnover,
        computed_metrics.working_capital AS working_capital_cr,
        raw_data.results_period,
        raw_data.shareholding_period,
        raw_data.last_updated
    FROM stocks
    JOIN raw_data ON raw_data.symbol = stocks.symbol
    LEFT JOIN computed_metrics ON computed_metrics.symbol = stocks.symbol
    LEFT JOIN technical_data ON technical_data.symbol = stocks.symbol AND technical_data.timeframe = 'daily'
    """

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY raw_data.market_cap DESC"
    if limit is not None:
        sql += f" LIMIT {max(1, min(limit, 5000))}"

    conn = get_db_connection()
    try:
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        total = conn.execute("SELECT COUNT(*) FROM raw_data").fetchone()[0]
    finally:
        conn.close()

    return {
        "results": rows,
        "count": len(rows),
        "meta": {
            "source": "screener_local_db",
            "query_filters": parsed_filters,
            "symbol_count": total,
            "matches_before_limit": len(rows) if limit is not None else len(rows),
            "matches_returned": len(rows),
        },
    }
