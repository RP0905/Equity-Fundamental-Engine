from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from io import BytesIO
import math
import re
from typing import Any

import pandas as pd
import requests


MASTER_SHEET_ID = "1QYs69eiWyYO6IireGHEl1HZn6um69gXrYOE_PjlBNLM"
MASTER_EXPORT_URL = f"https://docs.google.com/spreadsheets/d/{MASTER_SHEET_ID}/export?format=csv"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"


def _session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    return session


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def _clean_company_name(value: str) -> str:
    cleaned = (value or "").strip()
    cleaned = re.sub(r"\b(ltd|limited|ltd\.|inc|corp|corporation|co|company|plc)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[&]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_sheet_id(sheet_url: str) -> str | None:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url or "")
    return match.group(1) if match else None


def _safe_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return None
    if isinstance(value, complex):
        if abs(value.imag) > 1e-9:
            return None
        value = value.real
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("%", "").strip()
        if not cleaned:
            return None
        try:
            parsed = float(cleaned)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_div(numerator: float | None, denominator: float | None, pct: bool = False) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    numerator = _safe_float(numerator)
    denominator = _safe_float(denominator)
    if numerator is None or denominator in (None, 0):
        return None
    value = numerator / denominator
    if not math.isfinite(value):
        return None
    return round(value * 100, 2) if pct else round(value, 4)


def _format_period(value: Any, quarterly: bool = False) -> str:
    if isinstance(value, pd.Timestamp):
        return value.strftime("%b %Y") if quarterly else f"FY{value.year}"
    return str(value)


def _build_series(labels: list[str], values: list[Any]) -> dict[str, list[Any]]:
    return {"labels": labels, "values": [None if pd.isna(v) else _safe_float(v) for v in values]}


def _cagr(values: list[float | None], years: int) -> float | None:
    if len(values) <= years:
        return None
    end = values[-1]
    start = values[-1 - years]
    start = _safe_float(start)
    end = _safe_float(end)
    if start in (None, 0) or end is None or start <= 0 or end <= 0:
        return None
    return round((((end / start) ** (1 / years)) - 1) * 100, 2)


def _yoy(values: list[float | None]) -> list[float | None]:
    result: list[float | None] = []
    for idx, value in enumerate(values):
        if idx == 0 or value is None or values[idx - 1] in (None, 0):
            result.append(None)
            continue
        result.append(round(((value - values[idx - 1]) / values[idx - 1]) * 100, 2))
    return result


def _latest(values: list[float | None]) -> float | None:
    return values[-1] if values else None


def _previous(values: list[float | None]) -> float | None:
    return values[-2] if len(values) > 1 else None


def _metric_card(label: str, values: list[float | None], suffix: str | None = None) -> dict[str, Any]:
    latest = _latest(values)
    previous = _previous(values)
    delta = None
    if latest is not None and previous is not None:
        delta = round(latest - previous, 2)
    return {"label": label, "value": latest, "delta": delta, "suffix": suffix}


@lru_cache(maxsize=1)
def load_master_index() -> list[dict[str, str]]:
    df = pd.read_csv(MASTER_EXPORT_URL)
    rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        name = str(row.get("Stock Name") or "").strip()
        url = str(row.get("Spreadsheet URL") or "").strip()
        if not name or not url:
            continue
        rows.append(
            {
                "name": name,
                "url": url,
                "sheet_id": _extract_sheet_id(url) or "",
                "normalized": _normalize(name),
            }
        )
    return rows


def search_master_index(query: str, limit: int = 8) -> list[dict[str, str]]:
    needle = _normalize(query)
    if not needle:
        return []
    scored = []
    for row in load_master_index():
        score = 0
        normalized = row["normalized"]
        if normalized == needle:
            score += 100
        elif normalized.startswith(needle):
            score += 70
        elif needle in normalized:
            score += 40
        score += int(SequenceMatcher(None, needle, normalized).ratio() * 30)
        scored.append((score, row))

    scored.sort(key=lambda item: (-item[0], len(item[1]["name"])))
    results = [row for score, row in scored if score > 0][:limit]
    return [{"name": row["name"], "sheetUrl": row["url"]} for row in results]


def resolve_company_entry(query: str) -> dict[str, str] | None:
    normalized = _normalize(query)
    if not normalized:
        return None

    for row in load_master_index():
        if row["normalized"] == normalized:
            return row

    ranked = search_master_index(query, limit=1)
    if not ranked:
        return None
    best_name = ranked[0]["name"]
    for row in load_master_index():
        if row["name"] == best_name:
            return row
    return None


@lru_cache(maxsize=64)
def _load_workbook(sheet_id: str) -> dict[str, pd.DataFrame]:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    content = _session().get(url, timeout=30).content
    excel = pd.ExcelFile(BytesIO(content))
    return {name: pd.read_excel(BytesIO(content), sheet_name=name, header=None) for name in excel.sheet_names}


def _row_values(df: pd.DataFrame, row_idx: int, col_refs: int | list[int]) -> list[float | None]:
    if isinstance(col_refs, int):
        columns = list(range(1, col_refs + 1))
    else:
        columns = col_refs
    values: list[float | None] = []
    for col in columns:
        values.append(_safe_float(df.iat[row_idx, col] if row_idx < len(df.index) and col < len(df.columns) else None))
    return values


def _period_layout(df: pd.DataFrame, row_idx: int, quarterly: bool = False) -> tuple[list[str], list[int]]:
    labels: list[str] = []
    cols: list[int] = []
    started = False
    col = 1
    while col < len(df.columns):
        value = df.iat[row_idx, col]
        if pd.isna(value):
            if not started:
                col += 1
                continue
            break
        if isinstance(value, pd.Timestamp):
            labels.append(_format_period(value, quarterly=quarterly))
            cols.append(col)
            started = True
            col += 1
            continue
        try:
            parsed = pd.to_datetime(value)
            labels.append(_format_period(parsed, quarterly=quarterly))
            cols.append(col)
            started = True
            col += 1
        except Exception:
            if started:
                break
            col += 1
    return labels, cols


def _statement_rows(df: pd.DataFrame, row_indices: dict[str, int], col_refs: int | list[int]) -> dict[str, list[float | None]]:
    return {label: _row_values(df, idx, col_refs) for label, idx in row_indices.items()}


def _parse_data_sheet(df: pd.DataFrame) -> dict[str, Any]:
    annual_labels, annual_cols = _period_layout(df, 15, quarterly=False)
    quarter_labels, quarter_cols = _period_layout(df, 40, quarterly=True)

    annual_rows = _statement_rows(
        df,
        {
            "sales": 16,
            "raw_material_cost": 17,
            "change_in_inventory": 18,
            "power_and_fuel": 19,
            "other_mfg_exp": 20,
            "employee_cost": 21,
            "selling_admin": 22,
            "other_expenses": 23,
            "other_income": 24,
            "depreciation": 25,
            "interest": 26,
            "pbt": 27,
            "tax": 28,
            "net_profit": 29,
            "dividend_amount": 30,
        },
        annual_cols,
    )

    quarterly_rows = _statement_rows(
        df,
        {
            "sales": 41,
            "expenses": 42,
            "other_income": 43,
            "depreciation": 44,
            "interest": 45,
            "pbt": 46,
            "tax": 47,
            "net_profit": 48,
            "operating_profit": 49,
        },
        quarter_cols,
    )

    balance_rows = _statement_rows(
        df,
        {
            "equity_capital": 56,
            "reserves": 57,
            "borrowings": 58,
            "other_liabilities": 59,
            "total_liabilities": 60,
            "net_block": 61,
            "cwip": 62,
            "investments": 63,
            "other_assets": 64,
            "total_assets": 65,
            "receivables": 66,
            "inventory": 67,
            "cash_bank": 68,
            "equity_shares": 69,
            "face_value_history": 71,
        },
        annual_cols,
    )

    cashflow_rows = _statement_rows(
        df,
        {
            "cfo": 81,
            "cfi": 82,
            "cff": 83,
            "net_cash_flow": 84,
        },
        annual_cols,
    )

    annual_prices = _row_values(df, 89, annual_cols)
    adjusted_shares = _row_values(df, 92, annual_cols)

    company_name = str(df.iat[0, 1]).strip()
    face_value = _safe_float(df.iat[6, 1])
    current_price = _safe_float(df.iat[7, 1])
    market_cap = _safe_float(df.iat[8, 1])
    number_of_shares = _safe_float(df.iat[5, 1])

    return {
        "company_name": company_name,
        "face_value": face_value,
        "current_price": current_price,
        "market_cap_cr": market_cap,
        "number_of_shares_cr": number_of_shares,
        "annual_labels": annual_labels,
        "quarter_labels": quarter_labels,
        "annual_rows": annual_rows,
        "quarterly_rows": quarterly_rows,
        "balance_rows": balance_rows,
        "cashflow_rows": cashflow_rows,
        "annual_prices": annual_prices,
        "adjusted_shares_cr": adjusted_shares,
    }


def _parse_profit_loss_sheet(df: pd.DataFrame) -> tuple[list[str], dict[str, list[float | None]]]:
    labels, cols = _period_layout(df, 2, quarterly=False)
    return labels, _statement_rows(
        df,
        {
            "sales": 3,
            "expenses": 4,
            "operating_profit": 5,
            "other_income": 6,
            "depreciation": 7,
            "interest": 8,
            "pbt": 9,
            "tax": 10,
            "net_profit": 11,
            "eps": 12,
            "pe": 13,
            "price": 14,
            "dividend_payout_pct": 18,
            "opm_pct": 19,
        },
        cols,
    )


def _parse_quarters_sheet(df: pd.DataFrame) -> tuple[list[str], dict[str, list[float | None]]]:
    labels, cols = _period_layout(df, 2, quarterly=True)
    return labels, _statement_rows(
        df,
        {
            "sales": 3,
            "expenses": 4,
            "operating_profit": 5,
            "other_income": 6,
            "depreciation": 7,
            "interest": 8,
            "pbt": 9,
            "tax": 10,
            "net_profit": 11,
        },
        cols,
    )


def _calc_piotroski(calculated: dict[str, list[float | None]]) -> int | None:
    if len(calculated["net_profit"]) < 2:
        return None

    latest = -1
    prev = -2

    roa_latest = _safe_div(calculated["net_profit"][latest], calculated["total_assets"][latest], pct=False)
    roa_prev = _safe_div(calculated["net_profit"][prev], calculated["total_assets"][prev], pct=False)
    cfo_latest = calculated["cfo"][latest]
    cfo_assets = _safe_div(calculated["cfo"][latest], calculated["total_assets"][latest], pct=False)
    debt_eq_latest = _safe_div(calculated["borrowings"][latest], calculated["net_worth"][latest], pct=False)
    debt_eq_prev = _safe_div(calculated["borrowings"][prev], calculated["net_worth"][prev], pct=False)
    liquidity_latest = _safe_div(calculated["cash_bank"][latest], calculated["other_liabilities"][latest], pct=False)
    liquidity_prev = _safe_div(calculated["cash_bank"][prev], calculated["other_liabilities"][prev], pct=False)
    shares_latest = calculated["adjusted_shares_cr"][latest]
    shares_prev = calculated["adjusted_shares_cr"][prev]
    gm_latest = _safe_div(calculated["gross_profit_proxy"][latest], calculated["sales"][latest], pct=False)
    gm_prev = _safe_div(calculated["gross_profit_proxy"][prev], calculated["sales"][prev], pct=False)
    at_latest = _safe_div(calculated["sales"][latest], calculated["total_assets"][latest], pct=False)
    at_prev = _safe_div(calculated["sales"][prev], calculated["total_assets"][prev], pct=False)

    checks = [
        1 if (roa_latest or 0) > 0 else 0,
        1 if (cfo_latest or 0) > 0 else 0,
        1 if roa_latest is not None and roa_prev is not None and roa_latest > roa_prev else 0,
        1 if cfo_assets is not None and roa_latest is not None and cfo_assets > roa_latest else 0,
        1 if debt_eq_latest is not None and debt_eq_prev is not None and debt_eq_latest < debt_eq_prev else 0,
        1 if liquidity_latest is not None and liquidity_prev is not None and liquidity_latest > liquidity_prev else 0,
        1 if shares_latest is not None and shares_prev is not None and shares_latest <= shares_prev else 0,
        1 if gm_latest is not None and gm_prev is not None and gm_latest > gm_prev else 0,
        1 if at_latest is not None and at_prev is not None and at_latest > at_prev else 0,
    ]
    return sum(checks)


def _calculate_fundamentals(parsed: dict[str, Any], pnl_rows: dict[str, list[float | None]]) -> dict[str, Any]:
    annual_labels = parsed["annual_labels"]
    q_labels = parsed["quarter_labels"]

    sales = parsed["annual_rows"]["sales"]
    net_profit = parsed["annual_rows"]["net_profit"]
    depreciation = parsed["annual_rows"]["depreciation"]
    interest = parsed["annual_rows"]["interest"]
    tax = parsed["annual_rows"]["tax"]
    other_income = parsed["annual_rows"]["other_income"]
    dividend_amount = parsed["annual_rows"]["dividend_amount"]
    borrowings = parsed["balance_rows"]["borrowings"]
    equity_capital = parsed["balance_rows"]["equity_capital"]
    reserves = parsed["balance_rows"]["reserves"]
    other_liabilities = parsed["balance_rows"]["other_liabilities"]
    total_assets = parsed["balance_rows"]["total_assets"]
    net_block = parsed["balance_rows"]["net_block"]
    receivables = parsed["balance_rows"]["receivables"]
    cash_bank = parsed["balance_rows"]["cash_bank"]
    cfo = parsed["cashflow_rows"]["cfo"]
    adjusted_shares = parsed["adjusted_shares_cr"]
    annual_prices = parsed["annual_prices"]

    operating_profit: list[float | None] = []
    ebit: list[float | None] = []
    operating_margin: list[float | None] = []
    net_margin: list[float | None] = []
    gross_margin: list[float | None] = []
    eps: list[float | None] = []
    book_value_per_share: list[float | None] = []
    pe_series: list[float | None] = []
    pb_series: list[float | None] = []
    roe: list[float | None] = []
    roce: list[float | None] = []
    debt_to_equity: list[float | None] = []
    interest_coverage: list[float | None] = []
    cfo_to_pat: list[float | None] = []
    capex: list[float | None] = []
    fcf: list[float | None] = []
    dividend_payout: list[float | None] = []
    debtor_days: list[float | None] = []
    cash_conversion: list[float | None] = []
    net_debt: list[float | None] = []
    net_debt_to_ebitda: list[float | None] = []
    accrual_ratio: list[float | None] = []
    net_worth: list[float | None] = []
    capital_employed: list[float | None] = []
    gross_profit_proxy: list[float | None] = []

    for idx in range(len(annual_labels)):
        op_profit = pnl_rows["operating_profit"][idx]
        if op_profit is None:
            detail_total = sum(
                value or 0
                for value in [
                    parsed["annual_rows"]["power_and_fuel"][idx],
                    parsed["annual_rows"]["other_mfg_exp"][idx],
                    parsed["annual_rows"]["employee_cost"][idx],
                    parsed["annual_rows"]["selling_admin"][idx],
                    parsed["annual_rows"]["other_expenses"][idx],
                ]
            )
            op_profit = round((sales[idx] or 0) - detail_total, 2) if sales[idx] is not None else None

        nw = None if equity_capital[idx] is None or reserves[idx] is None else round(equity_capital[idx] + reserves[idx], 2)
        gp_proxy = None
        if sales[idx] is not None:
            gp_proxy = round(
                sales[idx]
                - (parsed["annual_rows"]["employee_cost"][idx] or 0)
                - (parsed["annual_rows"]["other_mfg_exp"][idx] or 0),
                2,
            )

        opm = _safe_div(op_profit, sales[idx], pct=True)
        nm = _safe_div(net_profit[idx], sales[idx], pct=True)
        gm = _safe_div(gp_proxy, sales[idx], pct=True)
        eb = None if op_profit is None or depreciation[idx] is None else round(op_profit - depreciation[idx], 2)
        eps_value = _safe_div(net_profit[idx], adjusted_shares[idx], pct=False)
        bvps = _safe_div(nw, adjusted_shares[idx], pct=False)
        pe_value = _safe_div(annual_prices[idx], eps_value, pct=False)
        pb_value = _safe_div(annual_prices[idx], bvps, pct=False)
        roe_value = _safe_div(net_profit[idx], nw, pct=True)
        ce = None if total_assets[idx] is None or other_liabilities[idx] is None else round(total_assets[idx] - other_liabilities[idx], 2)
        roce_value = _safe_div(eb, ce, pct=True)
        de_value = _safe_div(borrowings[idx], nw, pct=False)
        ic_value = _safe_div(eb, interest[idx], pct=False)
        cfo_pat_value = _safe_div(cfo[idx], net_profit[idx], pct=False)
        if idx == 0 or net_block[idx] is None or net_block[idx - 1] is None or depreciation[idx] is None:
            capex_value = None
        else:
            capex_value = round(net_block[idx] - net_block[idx - 1] + depreciation[idx], 2)
        fcf_value = None if cfo[idx] is None or capex_value is None else round(cfo[idx] - capex_value, 2)
        div_payout_value = _safe_div(dividend_amount[idx], net_profit[idx], pct=True)
        debtor_days_value = _safe_div(receivables[idx], sales[idx], pct=False)
        if debtor_days_value is not None:
            debtor_days_value = round(debtor_days_value * 365, 2)
        cash_conv_value = _safe_div(cash_bank[idx], total_assets[idx], pct=True)
        net_debt_value = None if borrowings[idx] is None or cash_bank[idx] is None else round(borrowings[idx] - cash_bank[idx], 2)
        nd_ebitda_value = _safe_div(net_debt_value, op_profit, pct=False)
        accrual_value = None
        if cfo[idx] is not None and net_profit[idx] is not None and total_assets[idx] not in (None, 0):
            accrual_value = round((cfo[idx] - net_profit[idx]) / total_assets[idx], 4)

        operating_profit.append(op_profit)
        ebit.append(eb)
        operating_margin.append(opm)
        net_margin.append(nm)
        gross_margin.append(gm)
        eps.append(eps_value)
        book_value_per_share.append(bvps)
        pe_series.append(pe_value)
        pb_series.append(pb_value)
        roe.append(roe_value)
        roce.append(roce_value)
        debt_to_equity.append(de_value)
        interest_coverage.append(ic_value)
        cfo_to_pat.append(cfo_pat_value)
        capex.append(capex_value)
        fcf.append(fcf_value)
        dividend_payout.append(div_payout_value)
        debtor_days.append(debtor_days_value)
        cash_conversion.append(cash_conv_value)
        net_debt.append(net_debt_value)
        net_debt_to_ebitda.append(nd_ebitda_value)
        accrual_ratio.append(accrual_value)
        net_worth.append(nw)
        capital_employed.append(ce)
        gross_profit_proxy.append(gp_proxy)

    revenue_yoy = _yoy(sales)
    profit_yoy = _yoy(net_profit)
    piotroski = _calc_piotroski(
        {
            "net_profit": net_profit,
            "total_assets": total_assets,
            "cfo": cfo,
            "borrowings": borrowings,
            "net_worth": net_worth,
            "cash_bank": cash_bank,
            "other_liabilities": other_liabilities,
            "adjusted_shares_cr": adjusted_shares,
            "gross_profit_proxy": gross_profit_proxy,
            "sales": sales,
        }
    )

    annual_chart = []
    for idx, label in enumerate(annual_labels):
        annual_chart.append(
            {
                "period": label,
                "sales": sales[idx],
                "netProfit": net_profit[idx],
                "operatingProfit": operating_profit[idx],
                "grossMargin": gross_margin[idx],
                "operatingMargin": operating_margin[idx],
                "netMargin": net_margin[idx],
            }
        )

    quarter_chart = []
    quarter_sales = parsed["quarterly_rows"]["sales"]
    quarter_net = parsed["quarterly_rows"]["net_profit"]
    quarter_op = parsed["quarterly_rows"]["operating_profit"]
    for idx, label in enumerate(q_labels):
        quarter_chart.append(
            {
                "period": label,
                "sales": quarter_sales[idx],
                "netProfit": quarter_net[idx],
                "operatingProfit": quarter_op[idx],
            }
        )

    latest_market_cap = parsed["market_cap_cr"]
    latest_fcf_yield = _safe_div(_latest(fcf), latest_market_cap, pct=True)

    return {
        "annual_labels": annual_labels,
        "quarter_labels": q_labels,
        "annual_chart": annual_chart,
        "quarter_chart": quarter_chart,
        "sales": sales,
        "net_profit": net_profit,
        "operating_profit": operating_profit,
        "gross_margin": gross_margin,
        "operating_margin": operating_margin,
        "net_margin": net_margin,
        "ebit": ebit,
        "eps": eps,
        "book_value_per_share": book_value_per_share,
        "pe_series": pe_series,
        "pb_series": pb_series,
        "roe": roe,
        "roce": roce,
        "debt_to_equity": debt_to_equity,
        "interest_coverage": interest_coverage,
        "cfo_to_pat": cfo_to_pat,
        "capex": capex,
        "fcf": fcf,
        "dividend_payout": dividend_payout,
        "dividend_amount": dividend_amount,
        "revenue_yoy": revenue_yoy,
        "profit_yoy": profit_yoy,
        "revenue_cagr_3y": _cagr(sales, 3),
        "revenue_cagr_5y": _cagr(sales, 5),
        "revenue_cagr_10y": _cagr(sales, 10),
        "profit_cagr_3y": _cagr(net_profit, 3),
        "profit_cagr_5y": _cagr(net_profit, 5),
        "profit_cagr_10y": _cagr(net_profit, 10),
        "debtor_days": debtor_days,
        "cash_conversion": cash_conversion,
        "net_debt": net_debt,
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "accrual_ratio": accrual_ratio,
        "piotroski": piotroski,
        "fcf_yield_latest": latest_fcf_yield,
        "cfo": cfo,
        "net_worth": net_worth,
        "borrowings": borrowings,
        "other_liabilities": other_liabilities,
        "total_assets": total_assets,
        "cash_bank": cash_bank,
        "receivables": receivables,
        "adjusted_shares_cr": adjusted_shares,
        "annual_prices": annual_prices,
        "other_income": other_income,
        "depreciation": depreciation,
        "interest": interest,
        "pbt": parsed["annual_rows"]["pbt"],
        "tax": tax,
        "equity_capital": equity_capital,
        "reserves": reserves,
        "total_liabilities": parsed["balance_rows"]["total_liabilities"],
        "net_block": net_block,
        "cwip": parsed["balance_rows"]["cwip"],
        "investments": parsed["balance_rows"]["investments"],
        "other_assets": parsed["balance_rows"]["other_assets"],
        "inventory": parsed["balance_rows"]["inventory"],
        "net_cash_flow": parsed["cashflow_rows"]["net_cash_flow"],
        "cfi": parsed["cashflow_rows"]["cfi"],
        "cff": parsed["cashflow_rows"]["cff"],
    }


def _ownership_from_info(info: dict[str, Any]) -> dict[str, Any]:
    promoter = info.get("heldPercentInsiders")
    fii = info.get("heldPercentInstitutions")
    promoter_pct = round(promoter * 100, 2) if promoter is not None else None
    fii_pct = round(fii * 100, 2) if fii is not None else None
    public_pct = None
    if promoter_pct is not None or fii_pct is not None:
        public_pct = round(max(0, 100 - (promoter_pct or 0) - (fii_pct or 0)), 2)

    return {
        "period": "Latest available",
        "promoter": promoter_pct,
        "fii": fii_pct,
        "dii": None,
        "public": public_pct,
        "mfSchemes": None,
        "promoterPledge": None,
        "promoterChangeQoq": None,
        "source": "Yahoo Finance proxies",
    }


def _search_yahoo_quotes(search_term: str) -> list[dict[str, Any]]:
    if not search_term:
        return []
    params = {"q": search_term, "quotesCount": 10, "newsCount": 0, "listsCount": 0}
    response = _session().get(YAHOO_SEARCH_URL, params=params, timeout=15)
    return response.json().get("quotes", [])


MANUAL_YAHOO_SYMBOLS = {
    "tatamotors": "TMCV.NS",
    "garwaretechnicalfibres": "GARFIBRES.NS",
    "garwaretech": "GARFIBRES.NS",
    "relianceindustries": "RELIANCE.NS",
}


def _resolve_yahoo_symbol(query: str, company_name: str) -> str | None:
    cleaned = query.strip().upper()
    if cleaned.endswith((".NS", ".BO")):
        return cleaned

    best_symbol = None
    best_score = -1
    target_name = _normalize(_clean_company_name(company_name or query))
    if target_name in MANUAL_YAHOO_SYMBOLS:
        return MANUAL_YAHOO_SYMBOLS[target_name]

    search_terms = []
    for value in [company_name, _clean_company_name(company_name), query, _clean_company_name(query)]:
        value = (value or "").strip()
        if value and value not in search_terms:
            search_terms.append(value)

    quotes: list[dict[str, Any]] = []
    for term in search_terms:
        quotes.extend(_search_yahoo_quotes(term))

    if not quotes:
        return cleaned

    for quote in quotes:
        if quote.get("quoteType") != "EQUITY":
            continue
        symbol = quote.get("symbol") or ""
        exchange = (quote.get("exchange") or "") + " " + (quote.get("exchDisp") or "")
        long_name = quote.get("longname") or quote.get("shortname") or ""
        short_name = quote.get("shortname") or ""
        long_name_norm = _normalize(_clean_company_name(long_name))
        short_name_norm = _normalize(_clean_company_name(short_name))
        symbol_base = _normalize(symbol.replace(".NS", "").replace(".BO", ""))

        score = 0
        if symbol.endswith(".NS"):
            score += 6
        elif symbol.endswith(".BO"):
            score += 5
        if "NSE" in exchange.upper():
            score += 4
        if "BSE" in exchange.upper():
            score += 3
        if long_name_norm == target_name:
            score += 8
        elif target_name and target_name in long_name_norm:
            score += 4
        if short_name_norm == target_name:
            score += 8
        elif target_name and target_name in short_name_norm:
            score += 4
        if symbol_base == target_name:
            score += 10
        score += int(SequenceMatcher(None, target_name, long_name_norm).ratio() * 10)
        score += int(SequenceMatcher(None, target_name, short_name_norm).ratio() * 10)

        if score > best_score:
            best_score = score
            best_symbol = symbol

    return best_symbol or cleaned


def _compute_dividend_yield(current_price: float | None, dividend_amount: float | None, shares_cr: float | None) -> float | None:
    if current_price in (None, 0) or dividend_amount is None or shares_cr in (None, 0):
        return None
    dividend_per_share = dividend_amount / shares_cr
    return round((dividend_per_share / current_price) * 100, 2)


def _first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _yahoo_statement_values(df: pd.DataFrame, row_name: str) -> tuple[list[str], list[float | None]]:
    if df is None or df.empty or row_name not in df.index:
        return [], []
    series = df.loc[row_name]
    cols = list(series.index)[::-1]
    labels = []
    values = []
    for col in cols:
        label = _format_period(col, quarterly=False) if hasattr(col, "year") else str(col)
        labels.append(label)
        values.append(_safe_float(series[col]))
    return labels, values


def _apply_yahoo_fallback(payload: dict[str, Any], yahoo_bundle: dict[str, Any]) -> dict[str, Any]:
    financials = yahoo_bundle.get("financials")
    balance = yahoo_bundle.get("balance_sheet")
    cashflow = yahoo_bundle.get("cashflow")
    info = yahoo_bundle.get("info") or {}
    if financials is None or financials.empty:
        return payload

    labels, sales = _yahoo_statement_values(financials, "Total Revenue")
    if not labels or not sales:
        return payload

    def to_cr(values: list[float | None]) -> list[float | None]:
        return [round(value / 1e7, 2) if value is not None else None for value in values]

    _, net_profit = _yahoo_statement_values(financials, "Net Income")
    _, ebit = _yahoo_statement_values(financials, "EBIT")
    _, ebitda = _yahoo_statement_values(financials, "EBITDA")
    _, depreciation = _yahoo_statement_values(financials, "Reconciled Depreciation")
    _, interest = _yahoo_statement_values(financials, "Interest Expense")
    _, tax = _yahoo_statement_values(financials, "Tax Provision")
    _, pbt = _yahoo_statement_values(financials, "Pretax Income")
    _, other_income = _yahoo_statement_values(financials, "Other Non Operating Income Expenses")
    _, equity = _yahoo_statement_values(balance, "Common Stock Equity")
    _, debt = _yahoo_statement_values(balance, "Total Debt")
    _, cash = _yahoo_statement_values(balance, "Cash And Cash Equivalents")
    _, total_assets = _yahoo_statement_values(balance, "Total Assets")
    _, invested_capital = _yahoo_statement_values(balance, "Invested Capital")
    _, cfo = _yahoo_statement_values(cashflow, "Operating Cash Flow")
    _, fcf = _yahoo_statement_values(cashflow, "Free Cash Flow")
    _, capex = _yahoo_statement_values(cashflow, "Capital Expenditure")
    _, shares = _yahoo_statement_values(balance, "Ordinary Shares Number")

    sales_cr = to_cr(sales)
    net_profit_cr = to_cr(net_profit)
    ebit_cr = to_cr(ebit)
    ebitda_cr = to_cr(ebitda)
    depreciation_cr = to_cr(depreciation)
    interest_cr = to_cr(interest)
    tax_cr = to_cr(tax)
    pbt_cr = to_cr(pbt)
    other_income_cr = to_cr(other_income)
    equity_cr = to_cr(equity)
    debt_cr = to_cr(debt)
    cash_cr = to_cr(cash)
    total_assets_cr = to_cr(total_assets)
    invested_capital_cr = to_cr(invested_capital)
    cfo_cr = to_cr(cfo)
    fcf_cr = to_cr(fcf)
    capex_cr = to_cr(capex)

    op_margin = [_safe_div(a, b, pct=True) for a, b in zip(ebitda_cr, sales_cr)]
    net_margin = [_safe_div(a, b, pct=True) for a, b in zip(net_profit_cr, sales_cr)]
    roe = [_safe_div(a, b, pct=True) for a, b in zip(net_profit_cr, equity_cr)]
    roce = [_safe_div(a, b, pct=True) for a, b in zip(ebit_cr, invested_capital_cr)]
    debt_equity = [_safe_div(a, b, pct=False) for a, b in zip(debt_cr, equity_cr)]
    interest_coverage = [_safe_div(a, b, pct=False) for a, b in zip(ebit_cr, interest_cr)]
    cfo_pat = [_safe_div(a, b, pct=False) for a, b in zip(cfo_cr, net_profit_cr)]
    eps = [_safe_div(a, b, pct=False) for a, b in zip(net_profit, shares)]
    bvps = [_safe_div(a, b, pct=False) for a, b in zip(equity, shares)]
    fcf_yield = _safe_div(_latest(fcf_cr), payload["valuation"].get("marketCapCr"), pct=True)

    payload["metricsGrid"] = [
        {"label": "ROE", "value": _latest(roe), "delta": None, "suffix": "%"},
        {"label": "ROCE", "value": _latest(roce), "delta": None, "suffix": "%"},
        {"label": "Net Margin", "value": _latest(net_margin), "delta": None, "suffix": "%"},
        {"label": "Operating Margin", "value": _latest(op_margin), "delta": None, "suffix": "%"},
        {"label": "Debt/Equity", "value": _latest(debt_equity), "delta": None, "suffix": "x"},
        {"label": "Interest Coverage", "value": _latest(interest_coverage), "delta": None, "suffix": "x"},
        {"label": "CFO/PAT", "value": _latest(cfo_pat), "delta": None, "suffix": "x"},
        {"label": "FCF Yield", "value": fcf_yield, "delta": None, "suffix": "%"},
        {"label": "Revenue Growth 3Y CAGR", "value": _cagr(sales, 2), "delta": None, "suffix": "%"},
        {"label": "PAT Growth 3Y CAGR", "value": _cagr(net_profit, 2), "delta": None, "suffix": "%"},
        {"label": "EPS TTM", "value": info.get("trailingEps") or _latest(eps), "delta": None, "suffix": ""},
        {"label": "Book Value", "value": _latest(bvps), "delta": None, "suffix": ""},
        {"label": "Dividend Yield", "value": payload["valuation"].get("dividendYield"), "delta": None, "suffix": "%"},
        {"label": "Piotroski Score", "value": None, "delta": None, "suffix": "/9"},
        {"label": "Promoter Holding", "value": payload["ownership"].get("promoter"), "delta": None, "suffix": "%"},
        {"label": "FII Holding", "value": payload["ownership"].get("fii"), "delta": None, "suffix": "%"},
    ]

    payload["statements"]["annualPnl"] = {
        "columns": labels,
        "rows": {
            "Sales": sales_cr,
            "Operating Profit": ebitda_cr,
            "OPM %": op_margin,
            "Other Income": other_income_cr,
            "Depreciation": depreciation_cr,
            "Interest": interest_cr,
            "PBT": pbt_cr,
            "Tax": tax_cr,
            "Net Profit": net_profit_cr,
            "EPS": eps,
        },
    }
    payload["statements"]["balanceSheet"] = {
        "columns": labels,
        "rows": {
            "Borrowings": debt_cr,
            "Cash & Bank": cash_cr,
            "Total Assets": total_assets_cr,
            "Net Debt": [None if d is None or c is None else round(d - c, 2) for d, c in zip(debt_cr, cash_cr)],
            "ROE %": roe,
            "ROCE %": roce,
        },
    }
    payload["statements"]["cashFlow"] = {
        "columns": labels,
        "rows": {
            "Cash from Operations": cfo_cr,
            "FCF": fcf_cr,
            "Capex": capex_cr,
            "CFO/PAT Ratio": cfo_pat,
        },
    }
    payload["charts"]["annual"] = [
        {"period": label, "sales": sales_cr[idx], "netProfit": net_profit_cr[idx] if idx < len(net_profit_cr) else None, "operatingProfit": ebitda_cr[idx] if idx < len(ebitda_cr) else None, "grossMargin": None, "operatingMargin": op_margin[idx] if idx < len(op_margin) else None, "netMargin": net_margin[idx] if idx < len(net_margin) else None}
        for idx, label in enumerate(labels)
    ]
    return payload


def build_sheet_payload(query: str, yahoo_bundle_getter, technicals_getter) -> dict[str, Any] | None:
    entry = resolve_company_entry(query)
    if not entry:
        return None

    workbook = _load_workbook(entry["sheet_id"])
    data_sheet = _parse_data_sheet(workbook["Data Sheet"])
    _, pnl_rows = _parse_profit_loss_sheet(workbook["Profit & Loss"])
    _, quarter_rows = _parse_quarters_sheet(workbook["Quarters"])
    calculated = _calculate_fundamentals(data_sheet, pnl_rows)

    yahoo_symbol = _resolve_yahoo_symbol(query, data_sheet["company_name"])
    yahoo_bundle = yahoo_bundle_getter(yahoo_symbol) if yahoo_symbol else None
    yahoo_info = yahoo_bundle["info"] if yahoo_bundle else {}
    technicals = technicals_getter(yahoo_bundle["history"]) if yahoo_bundle else {}

    live_price = yahoo_info.get("currentPrice") or yahoo_info.get("regularMarketPrice") or data_sheet["current_price"]
    previous_close = yahoo_info.get("previousClose") or yahoo_info.get("regularMarketPreviousClose")
    price_change = None
    price_change_pct = None
    if live_price is not None and previous_close not in (None, 0):
        price_change = round(live_price - previous_close, 2)
        price_change_pct = round((price_change / previous_close) * 100, 2)

    market_cap_live = yahoo_info.get("marketCap")
    market_cap_live_cr = round(market_cap_live / 1e7, 2) if market_cap_live else data_sheet["market_cap_cr"]
    latest_eps = _latest(calculated["eps"])
    latest_bvps = _latest(calculated["book_value_per_share"])
    latest_ebitda = _latest(calculated["operating_profit"])
    latest_net_debt = _latest(calculated["net_debt"])
    enterprise_value = yahoo_info.get("enterpriseValue")
    enterprise_value_cr = round(enterprise_value / 1e7, 2) if enterprise_value else (
        round(market_cap_live_cr + latest_net_debt, 2) if market_cap_live_cr is not None and latest_net_debt is not None else None
    )
    pe_live = yahoo_info.get("trailingPE") or (_safe_div(live_price, latest_eps, pct=False) if live_price is not None else None)
    pb_live = yahoo_info.get("priceToBook") or (_safe_div(live_price, latest_bvps, pct=False) if live_price is not None else None)
    ev_ebitda = yahoo_info.get("enterpriseToEbitda") or _safe_div(enterprise_value_cr, latest_ebitda, pct=False)
    dividend_yield = yahoo_info.get("dividendYield")
    if dividend_yield is None:
        dividend_yield = _compute_dividend_yield(
            live_price,
            _latest(calculated["dividend_amount"]),
            _latest(calculated["adjusted_shares_cr"]),
        )
    else:
        dividend_yield = round(dividend_yield * 100, 2) if dividend_yield <= 1 else round(dividend_yield, 2)
    ownership = _ownership_from_info(yahoo_info)
    roe_fallback = yahoo_info.get("returnOnEquity")
    roe_fallback = round(roe_fallback * 100, 2) if roe_fallback is not None else None
    roce_fallback = yahoo_info.get("returnOnAssets")
    roce_fallback = round(roce_fallback * 100, 2) if roce_fallback is not None else None

    metrics_cards = [
        {"label": "ROE", "value": _first_present(_latest(calculated["roe"]), roe_fallback), "delta": None, "suffix": "%"},
        {"label": "ROCE", "value": _first_present(_latest(calculated["roce"]), roce_fallback), "delta": None, "suffix": "%"},
        {"label": "Net Margin", "value": _latest(calculated["net_margin"]), "delta": None, "suffix": "%"},
        {"label": "Operating Margin", "value": _latest(calculated["operating_margin"]), "delta": None, "suffix": "%"},
        {"label": "Debt/Equity", "value": _latest(calculated["debt_to_equity"]), "delta": None, "suffix": "x"},
        {"label": "Interest Coverage", "value": _latest(calculated["interest_coverage"]), "delta": None, "suffix": "x"},
        {"label": "CFO/PAT", "value": _latest(calculated["cfo_to_pat"]), "delta": None, "suffix": "x"},
        {"label": "FCF Yield", "value": calculated["fcf_yield_latest"], "delta": None, "suffix": "%"},
        {"label": "Revenue Growth 3Y CAGR", "value": _first_present(calculated["revenue_cagr_3y"], calculated["revenue_cagr_5y"]), "delta": None, "suffix": "%"},
        {"label": "PAT Growth 3Y CAGR", "value": _first_present(calculated["profit_cagr_3y"], calculated["profit_cagr_5y"]), "delta": None, "suffix": "%"},
        {"label": "EPS TTM", "value": yahoo_info.get("trailingEps") or latest_eps, "delta": None, "suffix": ""},
        {"label": "Book Value", "value": _latest(calculated["book_value_per_share"]), "delta": None, "suffix": ""},
        {"label": "Dividend Yield", "value": dividend_yield, "delta": None, "suffix": "%"},
        {"label": "Piotroski Score", "value": calculated["piotroski"], "delta": None, "suffix": "/9"},
        {"label": "Promoter Holding", "value": ownership.get("promoter"), "delta": None, "suffix": "%"},
        {"label": "FII Holding", "value": ownership.get("fii"), "delta": None, "suffix": "%"},
    ]

    annual_table = {
        "columns": data_sheet["annual_labels"],
        "rows": {
            "Sales": calculated["sales"],
            "Expenses": pnl_rows["expenses"],
            "Operating Profit": calculated["operating_profit"],
            "OPM %": calculated["operating_margin"],
            "Other Income": calculated["other_income"],
            "Depreciation": calculated["depreciation"],
            "Interest": calculated["interest"],
            "PBT": calculated["pbt"],
            "Tax": calculated["tax"],
            "Net Profit": calculated["net_profit"],
            "EPS": calculated["eps"],
            "Dividend Payout %": calculated["dividend_payout"],
        },
    }

    balance_table = {
        "columns": data_sheet["annual_labels"],
        "rows": {
            "Equity Capital": calculated["equity_capital"],
            "Reserves": calculated["reserves"],
            "Borrowings": calculated["borrowings"],
            "Other Liabilities": calculated["other_liabilities"],
            "Total Liabilities": calculated["total_liabilities"],
            "Net Block": calculated["net_block"],
            "CWIP": calculated["cwip"],
            "Investments": calculated["investments"],
            "Other Assets": calculated["other_assets"],
            "Total Assets": calculated["total_assets"],
            "Receivables": calculated["receivables"],
            "Cash & Bank": calculated["cash_bank"],
            "Net Debt": calculated["net_debt"],
            "ROE %": calculated["roe"],
            "ROCE %": calculated["roce"],
        },
    }

    cashflow_table = {
        "columns": data_sheet["annual_labels"],
        "rows": {
            "Cash from Operations": calculated["cfo"],
            "Cash from Investing": calculated["cfi"],
            "Cash from Financing": calculated["cff"],
            "Net Cash Flow": calculated["net_cash_flow"],
            "CFO/PAT Ratio": calculated["cfo_to_pat"],
            "FCF": calculated["fcf"],
        },
    }

    timestamp = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    payload = {
        "company": {
            "name": data_sheet["company_name"],
            "query": query,
            "sheetUrl": entry["url"],
            "sheetId": entry["sheet_id"],
            "ticker": yahoo_symbol,
            "sector": yahoo_info.get("sector"),
            "industry": yahoo_info.get("industry"),
            "faceValue": data_sheet["face_value"],
            "currentPriceSheet": data_sheet["current_price"],
            "marketCapSheetCr": data_sheet["market_cap_cr"],
        },
        "price": {
            "current": live_price,
            "change": price_change,
            "changePct": price_change_pct,
            "weekHigh": yahoo_info.get("fiftyTwoWeekHigh"),
            "weekLow": yahoo_info.get("fiftyTwoWeekLow"),
            "volume": technicals.get("volume"),
        },
        "valuation": {
            "marketCapCr": market_cap_live_cr,
            "enterpriseValueCr": enterprise_value_cr,
            "peTtm": pe_live,
            "forwardPe": yahoo_info.get("forwardPE"),
            "pb": pb_live,
            "evEbitda": ev_ebitda,
            "beta": yahoo_info.get("beta"),
            "dividendYield": dividend_yield,
            "epsTtm": yahoo_info.get("trailingEps") or latest_eps,
            "forwardEps": yahoo_info.get("forwardEps"),
        },
        "analyst": {
            "consensus": yahoo_info.get("recommendationKey"),
            "targetPrice": yahoo_info.get("targetMeanPrice"),
            "ratingsCount": yahoo_info.get("numberOfAnalystOpinions"),
        },
        "ownership": ownership,
        "metricsGrid": metrics_cards,
        "charts": {
            "annual": calculated["annual_chart"],
            "quarterly": calculated["quarter_chart"],
        },
        "statements": {
            "annualPnl": annual_table,
            "balanceSheet": balance_table,
            "cashFlow": cashflow_table,
        },
        "technicals": technicals,
        "derived": {
            "piotroski": calculated["piotroski"],
            "revenueCagr3Y": calculated["revenue_cagr_3y"],
            "revenueCagr5Y": calculated["revenue_cagr_5y"],
            "revenueCagr10Y": calculated["revenue_cagr_10y"],
            "profitCagr3Y": calculated["profit_cagr_3y"],
            "profitCagr5Y": calculated["profit_cagr_5y"],
            "profitCagr10Y": calculated["profit_cagr_10y"],
            "revenueYoy": _latest(calculated["revenue_yoy"]),
            "profitYoy": _latest(calculated["profit_yoy"]),
            "bookValuePerShare": _latest(calculated["book_value_per_share"]),
            "ebitda": latest_ebitda,
            "ebit": _latest(calculated["ebit"]),
            "netDebt": _latest(calculated["net_debt"]),
            "netDebtToEbitda": _latest(calculated["net_debt_to_ebitda"]),
            "accrualRatio": _latest(calculated["accrual_ratio"]),
        },
        "quarterly": {
            "columns": data_sheet["quarter_labels"],
            "rows": {
                "Sales": quarter_rows["sales"],
                "Expenses": quarter_rows["expenses"],
                "Operating Profit": quarter_rows["operating_profit"],
                "Other Income": quarter_rows["other_income"],
                "Depreciation": quarter_rows["depreciation"],
                "Interest": quarter_rows["interest"],
                "PBT": quarter_rows["pbt"],
                "Tax": quarter_rows["tax"],
                "Net Profit": quarter_rows["net_profit"],
            },
        },
        "timestamp": timestamp,
    }
    if _latest(calculated["sales"]) is None:
        payload = _apply_yahoo_fallback(payload, yahoo_bundle or {})
    return payload
