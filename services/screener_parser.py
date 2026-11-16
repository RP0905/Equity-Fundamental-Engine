from __future__ import annotations

from datetime import datetime, timezone
import json
import re

from bs4 import BeautifulSoup
import requests


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value):
    return " ".join((value or "").replace("\xa0", " ").split())


def parse_number(value):
    if value is None:
        return None
    text = clean_text(str(value))
    if not text or text in {"-", "--"}:
        return None
    negative = "(" in text and ")" in text
    text = text.replace(",", "")
    text = text.replace("%", "")
    text = text.replace("₹", "")
    text = text.replace("Rs.", "")
    text = text.replace("Cr.", "")
    text = text.replace("Crores", "")
    text = text.replace("Crore", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    num = float(match.group(0))
    return -num if negative and num > 0 else num


def extract_embedded_json(html):
    patterns = [
        r"(?s)root\.App\s*=\s*(\{.*?\});",
        r"(?s)__NEXT_DATA__\"\s*type=\"application/json\">(.*?)</script>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if not match:
            continue
        try:
            return json.loads(match.group(1))
        except Exception:
            continue
    return None


def fetch_company_html(symbol, session=None):
    session = session or requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": USER_AGENT})

    urls = [
        f"https://www.screener.in/company/{symbol}/consolidated/",
        f"https://www.screener.in/company/{symbol}/",
    ]

    last_error = None
    for url in urls:
        try:
            response = session.get(url, timeout=30)
            if response.status_code == 200 and "screener" in response.url:
                return response.text, response.url
            last_error = RuntimeError(f"{response.status_code} for {url}")
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError(f"Failed to fetch Screener page for {symbol}")


def _parse_ratio_blocks(soup):
    data = {}
    for li in soup.select("ul.company-ratios li"):
        name_tag = li.select_one(".name")
        value_tag = li.select_one(".value, .nowrap")
        if not name_tag or not value_tag:
            continue
        name = clean_text(name_tag.get_text(" ", strip=True))
        raw_value = clean_text(value_tag.get_text(" ", strip=True))
        data[name] = raw_value

    # Generic fallback for future layout drift.
    if not data:
        for li in soup.find_all("li"):
            text = clean_text(li.get_text(" ", strip=True))
            if not text:
                continue
            if any(label in text for label in ("Current Price", "Market Cap", "Stock P/E", "ROCE", "ROE", "Dividend Yield", "Face Value")):
                parts = re.split(r"\s{2,}|(?<=\D)(?=\d)", text, maxsplit=1)
                if len(parts) == 2:
                    data[clean_text(parts[0])] = clean_text(parts[1])
    return data


def _table_to_records(table):
    headers = [clean_text(th.get_text(" ", strip=True)) for th in table.select("thead th")]
    if len(headers) < 2:
        first_row = table.select_one("tr")
        if first_row:
            headers = [clean_text(cell.get_text(" ", strip=True)) for cell in first_row.find_all(["th", "td"])]

    period_headers = headers[1:]
    rows = []
    for display_order, tr in enumerate(table.select("tbody tr"), start=1):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        metric = clean_text(cells[0].get_text(" ", strip=True))
        if not metric:
            continue
        for idx, cell in enumerate(cells[1:]):
            period_label = period_headers[idx] if idx < len(period_headers) else f"P{idx+1}"
            raw_value = clean_text(cell.get_text(" ", strip=True))
            rows.append(
                {
                    "metric": metric,
                    "period_label": period_label,
                    "value": parse_number(raw_value),
                    "raw_value": raw_value,
                    "display_order": display_order,
                }
            )
    return rows


def _find_table_after_heading(soup, heading_text):
    heading = soup.find(lambda tag: tag.name in {"h2", "h3"} and heading_text.lower() in clean_text(tag.get_text(" ", strip=True)).lower())
    if not heading:
        return None
    next_table = heading.find_next("table")
    return next_table


def _statement_map(rows):
    by_metric = {}
    for row in rows:
        by_metric.setdefault(row["metric"], []).append(row)
    return by_metric


def _latest_value(rows, *candidates):
    for candidate in candidates:
        candidate_rows = rows.get(candidate, [])
        for row in candidate_rows:
            if row["value"] is not None:
                return row["value"]
    return None


def _parse_shareholding(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["period_label"], {})
        metric = row["metric"].lower()
        value = row["value"]
        if value is None:
            continue
        if "promoter" in metric:
            grouped[row["period_label"]]["promoter_holding"] = value
        elif "fii" in metric or "fpi" in metric or "foreign" in metric:
            grouped[row["period_label"]]["fii_holding"] = value
        elif "dii" in metric or "domestic" in metric:
            grouped[row["period_label"]]["dii_holding"] = value
        elif "public" in metric:
            grouped[row["period_label"]]["public_holding"] = value
    return grouped


def _series_values(rows, *candidates):
    for candidate in candidates:
        candidate_rows = rows.get(candidate, [])
        values = [row["value"] for row in candidate_rows if row["value"] is not None]
        if values:
            return values
    return []


def _compute_cagr(values, years):
    if len(values) <= years:
        return None
    start = values[-(years + 1)]
    end = values[-1]
    if start in (None, 0) or start <= 0:
        return None
    return ((end / start) ** (1 / years) - 1) * 100


def _compute_latest_qtr_yoy(values):
    if len(values) < 5:
        return None
    start = values[-5]
    end = values[-1]
    if start in (None, 0):
        return None
    return ((end / start) - 1) * 100


def parse_company_page(html, symbol, page_url=None):
    soup = BeautifulSoup(html, "lxml")
    ratio_map = _parse_ratio_blocks(soup)

    company_name = None
    h1 = soup.find("h1")
    if h1:
        company_name = clean_text(h1.get_text(" ", strip=True))

    quarterly_rows = _table_to_records(_find_table_after_heading(soup, "Quarterly Results") or BeautifulSoup("<table></table>", "lxml").table)
    profit_loss_rows = _table_to_records(_find_table_after_heading(soup, "Profit & Loss") or BeautifulSoup("<table></table>", "lxml").table)
    balance_sheet_rows = _table_to_records(_find_table_after_heading(soup, "Balance Sheet") or BeautifulSoup("<table></table>", "lxml").table)
    cash_flow_rows = _table_to_records(_find_table_after_heading(soup, "Cash Flow") or BeautifulSoup("<table></table>", "lxml").table)
    shareholding_rows = _table_to_records(_find_table_after_heading(soup, "Shareholding Pattern") or BeautifulSoup("<table></table>", "lxml").table)

    pl = _statement_map(profit_loss_rows)
    bs = _statement_map(balance_sheet_rows)
    cf = _statement_map(cash_flow_rows)
    qr = _statement_map(quarterly_rows)
    sh = _parse_shareholding(shareholding_rows)

    latest_shareholding_period = next(iter(sh.keys()), None)
    latest_shareholding = sh.get(latest_shareholding_period, {})

    equity_capital = _latest_value(bs, "Equity Capital", "Share Capital")
    reserves = _latest_value(bs, "Reserves", "Reserves and Surplus")
    total_assets = _latest_value(bs, "Total Assets")
    current_assets = _latest_value(bs, "Other Assets", "Current Assets")
    current_liabilities = _latest_value(bs, "Other Liabilities", "Current Liabilities")
    borrowings = _latest_value(bs, "Borrowings", "Borrowings +")
    cash_from_operations = _latest_value(cf, "Cash from Operating Activity", "Cash from Operations")
    capex = _latest_value(cf, "Fixed assets purchased", "Capital expenditure")

    annual_sales_values = _series_values(pl, "Sales", "Revenue")
    annual_profit_values = _series_values(pl, "Net Profit", "Profit after tax")
    quarterly_sales_values = _series_values(qr, "Sales", "Revenue")
    quarterly_profit_values = _series_values(qr, "Net Profit", "Profit after tax")

    current_price = parse_number(ratio_map.get("Current Price"))
    book_value_per_share = parse_number(ratio_map.get("Book Value"))

    raw_data = {
        "current_price": current_price,
        "market_cap": parse_number(ratio_map.get("Market Cap")),
        "pe_ratio": parse_number(ratio_map.get("Stock P/E") or ratio_map.get("P/E")),
        "pb_ratio": (current_price / book_value_per_share) if current_price and book_value_per_share else None,
        "dividend_yield": parse_number(ratio_map.get("Dividend Yield")),
        "roe": parse_number(ratio_map.get("ROE")),
        "roce": parse_number(ratio_map.get("ROCE")),
        "face_value": parse_number(ratio_map.get("Face Value")),
        "bvps": book_value_per_share,
        "revenue": _latest_value(pl, "Sales", "Revenue"),
        "net_profit": _latest_value(pl, "Net Profit", "Profit after tax"),
        "sales_latest_quarter": quarterly_sales_values[-1] if quarterly_sales_values else None,
        "pat_latest_quarter": quarterly_profit_values[-1] if quarterly_profit_values else None,
        "qtr_sales_growth_yoy": _compute_latest_qtr_yoy(quarterly_sales_values),
        "qtr_profit_growth_yoy": _compute_latest_qtr_yoy(quarterly_profit_values),
        "sales_growth_3y": _compute_cagr(annual_sales_values, 3),
        "sales_growth_5y": _compute_cagr(annual_sales_values, 5),
        "profit_growth_3y": _compute_cagr(annual_profit_values, 3),
        "profit_growth_5y": _compute_cagr(annual_profit_values, 5),
        "avg_roe_3y": None,
        "avg_roe_5y": None,
        "ebitda": _latest_value(pl, "Operating Profit"),
        "operating_profit": _latest_value(pl, "Operating Profit"),
        "gross_profit": _latest_value(pl, "Gross Profit"),
        "pbt": _latest_value(pl, "Profit before tax", "PBT"),
        "total_assets": total_assets,
        "total_liabilities": None if total_assets is None or equity_capital is None or reserves is None else total_assets - (equity_capital + reserves),
        "equity": None if equity_capital is None or reserves is None else equity_capital + reserves,
        "reserves": reserves,
        "borrowings": borrowings,
        "cash_flow": cash_from_operations,
        "cash_flow_operating": cash_from_operations,
        "capex": capex,
        "promoter_holding": latest_shareholding.get("promoter_holding"),
        "fii_holding": latest_shareholding.get("fii_holding"),
        "dii_holding": latest_shareholding.get("dii_holding"),
        "public_holding": latest_shareholding.get("public_holding"),
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "interest_expense": _latest_value(pl, "Interest", "Interest Expense"),
        "results_period": next((row["period_label"] for row in quarterly_rows if row["value"] is not None), None),
        "shareholding_period": latest_shareholding_period,
        "statement_source": page_url,
        "last_updated": utc_now_iso(),
    }

    if raw_data["revenue"]:
        if raw_data["net_profit"] is not None:
            raw_data["net_profit_margin"] = (raw_data["net_profit"] / raw_data["revenue"]) * 100
        if raw_data["operating_profit"] is not None:
            raw_data["opm"] = (raw_data["operating_profit"] / raw_data["revenue"]) * 100
        if raw_data["gross_profit"] is not None:
            raw_data["gross_margin"] = (raw_data["gross_profit"] / raw_data["revenue"]) * 100
    if raw_data["net_profit"] is not None and raw_data["market_cap"] and raw_data["pe_ratio"]:
        shares = raw_data["market_cap"] / current_price if current_price else None
        raw_data["eps"] = raw_data["net_profit"] / shares if shares else None

    earnings_yield = None
    if raw_data["pe_ratio"] and raw_data["pe_ratio"] > 0:
        earnings_yield = 100.0 / raw_data["pe_ratio"]

    debt_to_equity = None
    if raw_data["borrowings"] is not None and raw_data["equity"]:
        debt_to_equity = raw_data["borrowings"] / raw_data["equity"]

    current_ratio = None
    if raw_data["current_assets"] is not None and raw_data["current_liabilities"]:
        current_ratio = raw_data["current_assets"] / raw_data["current_liabilities"]

    interest_coverage = None
    if raw_data["operating_profit"] is not None and raw_data["interest_expense"]:
        interest_coverage = raw_data["operating_profit"] / raw_data["interest_expense"]

    asset_turnover = None
    if raw_data["revenue"] is not None and raw_data["total_assets"]:
        asset_turnover = raw_data["revenue"] / raw_data["total_assets"]

    working_capital = None
    if raw_data["current_assets"] is not None and raw_data["current_liabilities"] is not None:
        working_capital = raw_data["current_assets"] - raw_data["current_liabilities"]

    computed = {
        "earnings_yield": earnings_yield,
        "debt_to_equity": debt_to_equity,
        "current_ratio": current_ratio,
        "interest_coverage": interest_coverage,
        "asset_turnover": asset_turnover,
        "working_capital": working_capital,
        "last_updated": utc_now_iso(),
    }

    statements = {
        "quarterly_results": quarterly_rows,
        "profit_loss": profit_loss_rows,
        "balance_sheet": balance_sheet_rows,
        "cash_flow": cash_flow_rows,
    }

    return {
        "stock": {
            "stock_name": company_name or symbol,
            "symbol": symbol,
            "screener_url": page_url,
            "last_synced_at": utc_now_iso(),
            "last_error": None,
        },
        "raw_data": raw_data,
        "computed_metrics": computed,
        "shareholding_pattern": sh,
        "statements": statements,
    }
