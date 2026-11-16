from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import math

import pandas as pd

from services.local_db import get_db_connection, init_db


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_header(name):
    return " ".join(str(name or "").strip().lower().replace("_", " ").split())


def _clean_num(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "-", "--"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    for token in (",", "%", "₹", "rs.", "cr.", "crore", "crores"):
        text = text.replace(token, "")
        text = text.replace(token.upper(), "")
    text = text.replace("(", "").replace(")", "").strip()
    try:
        num = float(text)
    except Exception:
        return None
    return -num if negative and num > 0 else num


def _first_present(row, columns):
    for column in columns:
        if column in row and pd.notna(row[column]):
            return row[column]
    return None


def _extract_symbol(row):
    symbol = _first_present(
        row,
        [
            "nse code",
            "nsecode",
            "symbol",
            "ticker",
            "stock code",
            "stockcode",
            "name",
        ],
    )
    if symbol is None:
        return None
    symbol = str(symbol).strip().upper()
    if not symbol or symbol in {"NAN", "NONE"}:
        return None
    return symbol.replace(".NS", "").replace(".BO", "")


def _extract_name(row, symbol):
    name = _first_present(row, ["name", "company name", "stock name"])
    return str(name).strip() if name is not None else symbol


RAW_COLUMN_MAP = {
    "current_price": ["cmp rs.", "cmp", "current price", "current price rs", "price"],
    "market_cap": ["mar cap rs.cr.", "market capitalization", "market cap", "market cap rs.cr."],
    "pe_ratio": ["p/e", "stock p/e", "price to earning", "price to earnings"],
    "pb_ratio": ["price to book value", "p/b", "pbv"],
    "dividend_yield": ["div yld %", "dividend yield", "dividend yield %"],
    "roe": ["roe %", "roe"],
    "roce": ["roce %", "roce"],
    "roa": ["roa %", "return on assets", "roa"],
    "net_profit_margin": ["net profit margin %", "net margin %", "npm %", "net profit margin"],
    "opm": ["opm %", "operating profit margin %", "operating margin %", "opm"],
    "gross_margin": ["gross profit margin %", "gross margin %", "gross margin"],
    "ebitda_margin": ["ebitda margin %", "ebitda margin"],
    "face_value": ["face value"],
    "eps": ["eps", "eps rs.", "earnings per share"],
    "bvps": ["book value", "book value per share", "bvps"],
    "dps": ["dividend per share", "dps"],
    "revenue": ["sales rs.cr.", "sales", "revenue"],
    "net_profit": ["profit after tax rs.cr.", "net profit rs.cr.", "profit after tax", "net profit"],
    "sales_latest_quarter": ["sales qtr rs.cr.", "sales latest quarter"],
    "pat_latest_quarter": ["np qtr rs.cr.", "profit after tax latest quarter", "net profit latest quarter"],
    "qtr_sales_growth_yoy": ["qtr sales var %", "yoy quarterly sales growth"],
    "qtr_profit_growth_yoy": ["qtr profit var %", "yoy quarterly profit growth"],
    "qtr_sales_growth_qoq": ["qoq sales growth %", "qoq quarterly sales growth"],
    "qtr_profit_growth_qoq": ["qoq profit growth %", "qoq quarterly profit growth"],
    "sales_growth_3y": ["sales growth 3years", "sales var 3yrs %", "sales growth"],
    "sales_growth_5y": ["sales growth 5years", "sales var 5yrs %"],
    "profit_growth_3y": ["profit growth 3years", "profit var 3yrs %", "profit growth"],
    "profit_growth_5y": ["profit growth 5years", "profit var 5yrs %"],
    "avg_roe_3y": ["average return on equity 3years", "roe 3yr %", "roe 3yrs %", "roe 3yr"],
    "avg_roe_5y": ["average return on equity 5years", "roe 5yr %", "roe 5yrs %", "roe 5yr"],
    "ebitda": ["ebitda rs.cr.", "ebitda"],
    "operating_profit": ["op rs.cr.", "operating profit rs.cr.", "operating profit"],
    "gross_profit": ["gross profit rs.cr.", "gross profit"],
    "pbt": ["profit before tax rs.cr.", "pbt rs.cr.", "profit before tax", "pbt"],
    "total_assets": ["total assets rs.cr.", "total assets"],
    "total_liabilities": ["total liabilities rs.cr.", "total liabilities"],
    "equity": ["net worth rs.cr.", "equity rs.cr.", "equity"],
    "reserves": ["reserves rs.cr.", "reserves"],
    "borrowings": ["borrowings rs.cr.", "borrowings", "debt rs.cr.", "debt"],
    "cash_flow": ["cash from operations last year", "cash flow rs.cr.", "cash flow"],
    "capex": ["capital expenditure rs.cr.", "capex rs.cr.", "capex"],
    "promoter_holding": ["promoter holding %", "promoter holding"],
    "fii_holding": ["fii holding %", "fii holding", "fii/fpi holding %"],
    "dii_holding": ["dii holding %", "dii holding"],
    "public_holding": ["public holding %", "public holding"],
    "pledged_percentage": ["pledged percentage", "pledged percentage %", "pledged %"],
    "current_assets": ["current assets rs.cr.", "current assets"],
    "current_liabilities": ["current liabilities rs.cr.", "current liabilities"],
    "interest_expense": ["interest rs.cr.", "interest expense rs.cr.", "interest expense"],
    "week_high_52": ["52 week high", "52w high"],
    "week_low_52": ["52 week low", "52w low"],
    "week_change_52": ["52 week change", "52w change %"],
    "volume": ["volume"],
    "avg_volume": ["average volume", "avg volume"],
    "beta": ["beta"],
    "cash_flow_operating": ["cash from operations last year", "cash flow from operating", "cfo"],
    "cash_flow_investing": ["cash flow from investing", "cfi"],
    "cash_flow_financing": ["cash flow from financing", "cff"],
    "free_cash_flow": ["free cash flow", "fcf"],
    "cash": ["cash and cash equivalents", "cash"],
    "inventory": ["inventory rs.cr.", "inventory"],
    "receivables": ["receivables rs.cr.", "accounts receivable", "receivables"],
    "payables": ["payables rs.cr.", "accounts payable", "payables"],
    "price_to_sales": ["price to sales", "p/s"],
    "price_to_fcf": ["price to free cash flow", "p/fcf"],
    "ev_ebitda": ["ev/ebitda", "enterprise value to ebitda"],
    "enterprise_value": ["enterprise value", "ev rs.cr.", "ev"],
    "payout_ratio": ["payout ratio", "dividend payout ratio"],
    "dividend_growth": ["dividend growth rate", "dividend growth"],
}


COMPUTED_COLUMN_MAP = {
    "earnings_yield": ["earnings yield", "earnings yield %"],
    "debt_to_equity": ["debt / eq", "debt to equity", "debt/equity"],
    "current_ratio": ["current ratio"],
    "quick_ratio": ["quick ratio"],
    "cash_ratio": ["cash ratio"],
    "interest_coverage": ["interest coverage", "interest coverage ratio"],
    "asset_turnover": ["asset turnover"],
    "inventory_turnover": ["inventory turnover"],
    "receivables_turnover": ["receivables turnover"],
    "working_capital": ["working capital rs.cr.", "working capital"],
    "working_capital_turnover": ["working capital turnover"],
}


def _map_columns(df):
    normalized = {_normalize_header(col): col for col in df.columns}
    return normalized


def _extract_mapped_numeric(row, normalized_columns, aliases):
    for alias in aliases:
        actual = normalized_columns.get(alias)
        if actual is None:
            continue
        value = row.get(actual)
        num = _clean_num(value)
        if num is not None:
            return num
    return None


def import_screener_csv(csv_path):
    init_db()
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    df = pd.read_csv(path)
    normalized_columns = _map_columns(df)
    now = utc_now_iso()

    imported = 0
    failures = []

    conn = get_db_connection()
    try:
        for _, raw_row in df.iterrows():
            row = raw_row.to_dict()
            symbol = _extract_symbol({_normalize_header(k): v for k, v in row.items()})
            if not symbol:
                failures.append({"row": int(_), "error": "Missing NSE symbol"})
                continue

            stock_name = _extract_name({_normalize_header(k): v for k, v in row.items()}, symbol)

            raw_data = {"symbol": symbol, "last_updated": now}
            for field, aliases in RAW_COLUMN_MAP.items():
                raw_data[field] = _extract_mapped_numeric(row, normalized_columns, aliases)

            computed = {"symbol": symbol, "last_updated": now}
            for field, aliases in COMPUTED_COLUMN_MAP.items():
                computed[field] = _extract_mapped_numeric(row, normalized_columns, aliases)

            if computed["earnings_yield"] is None and raw_data.get("pe_ratio") and raw_data["pe_ratio"] > 0:
                computed["earnings_yield"] = 100.0 / raw_data["pe_ratio"]
            if computed["debt_to_equity"] is None and raw_data.get("borrowings") is not None and raw_data.get("equity"):
                computed["debt_to_equity"] = raw_data["borrowings"] / raw_data["equity"]
            if computed["current_ratio"] is None and raw_data.get("current_assets") is not None and raw_data.get("current_liabilities"):
                if raw_data["current_liabilities"] != 0:
                    computed["current_ratio"] = raw_data["current_assets"] / raw_data["current_liabilities"]
            if computed["interest_coverage"] is None and raw_data.get("operating_profit") is not None and raw_data.get("interest_expense"):
                if raw_data["interest_expense"] != 0:
                    computed["interest_coverage"] = raw_data["operating_profit"] / raw_data["interest_expense"]
            if computed["working_capital"] is None and raw_data.get("current_assets") is not None and raw_data.get("current_liabilities") is not None:
                computed["working_capital"] = raw_data["current_assets"] - raw_data["current_liabilities"]
            if computed["asset_turnover"] is None and raw_data.get("revenue") is not None and raw_data.get("total_assets"):
                if raw_data["total_assets"] != 0:
                    computed["asset_turnover"] = raw_data["revenue"] / raw_data["total_assets"]

            conn.execute(
                """
                INSERT INTO stocks (symbol, stock_name, source, last_synced_at, last_error)
                VALUES (?, ?, 'screener_csv', ?, NULL)
                ON CONFLICT(symbol) DO UPDATE SET
                    stock_name=excluded.stock_name,
                    source=excluded.source,
                    last_synced_at=excluded.last_synced_at,
                    last_error=NULL
                """,
                (symbol, stock_name, now),
            )

            raw_columns = list(raw_data.keys())
            raw_updates = ", ".join([f"{col}=excluded.{col}" for col in raw_columns if col != "symbol"])
            conn.execute(
                f"""
                INSERT INTO raw_data ({', '.join(raw_columns)})
                VALUES ({', '.join(['?'] * len(raw_columns))})
                ON CONFLICT(symbol) DO UPDATE SET {raw_updates}
                """,
                [raw_data[col] for col in raw_columns],
            )

            computed_columns = list(computed.keys())
            computed_updates = ", ".join([f"{col}=excluded.{col}" for col in computed_columns if col != "symbol"])
            conn.execute(
                f"""
                INSERT INTO computed_metrics ({', '.join(computed_columns)})
                VALUES ({', '.join(['?'] * len(computed_columns))})
                ON CONFLICT(symbol) DO UPDATE SET {computed_updates}
                """,
                [computed[col] for col in computed_columns],
            )

            imported += 1

        conn.execute(
            """
            INSERT INTO import_runs (source_type, source_path, row_count, imported_count, failed_count, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "screener_csv",
                str(path),
                int(len(df.index)),
                imported,
                len(failures),
                "Imported from Screener export CSV",
                now,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "source_path": str(path),
        "row_count": int(len(df.index)),
        "imported_count": imported,
        "failed_count": len(failures),
        "failures": failures[:20],
    }
