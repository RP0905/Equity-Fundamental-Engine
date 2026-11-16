from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import threading
import time

import pandas as pd
import requests
import yfinance as yf

from analysis.old_engine import fetch_nse_data, fetch_screener_data
from services.nse_universe import get_nse_eq_symbols_ns
from services.yf_bootstrap import configure_yfinance_cache

configure_yfinance_cache()

_tls = threading.local()
_BASIC_SNAPSHOT_CACHE = {}
_BASIC_CACHE_TTL_SEC = 15 * 60
_BSE_UNIVERSE_CACHE = {}
_BSE_DETAIL_CACHE = {}
_SCREENER_CACHE = {}

DEFAULT_INTERACTIVE_MAX_SYMBOLS_US = 150
BSE_STAGE1_METRICS = {
    "market_cap_cr", "pe", "roe", "pb", "eps", "opm", "price",
}

DEFAULT_INDIAN_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "LT.NS", "ITC.NS", "HINDUNILVR.NS", "BHARTIARTL.NS",
    "KOTAKBANK.NS", "AXISBANK.NS", "BAJFINANCE.NS", "ASIANPAINT.NS",
    "MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "SUNPHARMA.NS", "NTPC.NS",
    "POWERGRID.NS", "ULTRACEMCO.NS", "WIPRO.NS", "TECHM.NS", "NESTLEIND.NS",
    "ONGC.NS", "HCLTECH.NS", "TITAN.NS", "JSWSTEEL.NS", "ADANIENT.NS", "COALINDIA.NS",
]
DEFAULT_US_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "UNH",
    "XOM", "WMT", "PG", "HD", "MA", "BAC", "JNJ", "KO",
]

_SCREENER_PAYLOAD_KEYS = frozenset({
    "market", "limit", "query", "max_symbols", "parallel_workers", "use_sample_universe",
})

PARAMETER_ALIASES = {
    "market capitalization": "market_cap_cr", "market cap": "market_cap_cr",
    "price to earning": "pe", "price to earnings": "pe", "p/e": "pe", "pe": "pe",
    "dividend yield": "dividend_yield", "price to book value": "pb", "price to book": "pb", "p/b": "pb", "pb": "pb",
    "return on capital employed": "roce", "roce": "roce", "return on assets": "roa", "roa": "roa",
    "debt to equity": "debt_to_equity",
    "debt/equity": "debt_to_equity", "d/e": "debt_to_equity", "return on equity": "roe", "roe": "roe",
    "eps": "eps", "earnings per share": "eps", "debt": "debt_cr", "total debt": "debt_cr",
    "promoter holding": "promoter_holding",
    "change in promoter holding": "change_promoter_holding", "earnings yield": "earnings_yield",
    "pledged percentage": "pledged_percentage", "industry pe": "industry_pe",
    "sales growth": "sales_growth_3y", "revenue growth": "sales_growth_3y",
    "profit growth": "profit_growth_3y", "earnings growth": "profit_growth_3y",
    "current price": "price", "price": "price", "price to sales": "price_to_sales", "p/s": "price_to_sales",
    "price to free cash flow": "price_to_fcf", "p/fcf": "price_to_fcf",
    "evebitda": "ev_ebitda", "ev/ebitda": "ev_ebitda", "enterprise value to ebitda": "ev_ebitda",
    "enterprise value": "enterprise_value_cr", "ev": "enterprise_value_cr", "current ratio": "current_ratio",
    "interest coverage ratio": "interest_coverage", "interest coverage": "interest_coverage",
    "peg ratio": "peg_ratio", "return over 3months": "return_3m",
    "sales": "sales_cr", "revenue": "sales_cr", "opm": "opm", "operating margin": "opm",
    "operating profit margin": "opm", "profit after tax": "pat_cr", "pat": "pat_cr", "net profit": "pat_cr",
    "sales latest quarter": "sales_latest_qtr_cr", "profit after tax latest quarter": "pat_latest_qtr_cr",
    "yoy quarterly sales growth": "qtr_sales_growth_yoy", "yoy quarterly profit growth": "qtr_profit_growth_yoy",
    "sales growth 3years": "sales_growth_3y", "sales growth 5years": "sales_growth_5y",
    "revenue growth 3years": "sales_growth_3y", "revenue growth 5years": "sales_growth_5y",
    "profit growth 3years": "profit_growth_3y", "profit growth 5years": "profit_growth_5y",
    "earnings growth 3years": "profit_growth_3y", "earnings growth 5years": "profit_growth_5y",
    "average return on equity 5years": "avg_roe_5y", "average return on equity 3years": "avg_roe_3y",
    "average roe 5years": "avg_roe_5y", "average roe 3years": "avg_roe_3y",
    "return over 1year": "return_1y", "return over 3years": "return_3y",
    "return over 5years": "return_5y", "return over 6months": "return_6m",
}

UNSUPPORTED_LIVE_ALIASES = {
    "net profit margin", "gross profit margin", "ebitda margin",
    "book value per share", "bvps", "dividend per share", "dps",
    "quick ratio", "cash ratio", "fii holding", "dii holding", "public holding",
    "pledged percentage", "operating profit", "ebitda", "gross profit",
    "profit before tax", "pbt", "qoq quarterly sales growth",
    "qoq quarterly profit growth", "52 week high", "52 week low",
    "52 week change", "volume", "average volume", "beta", "rsi", "macd",
    "cash flow from operating", "cash flow from investing",
    "cash flow from financing", "free cash flow", "fcf",
    "cash and cash equivalents", "total assets", "total liabilities",
    "shareholders equity", "reserves", "inventory", "accounts receivable",
    "accounts payable", "asset turnover", "inventory turnover",
    "receivables turnover", "working capital", "working capital turnover",
    "payout ratio", "dividend payout ratio", "dividend growth rate",
}


def _safe_num(value):
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()
            if not value:
                return None
        return float(value)
    except Exception:
        return None


def _clean_exception_message(exc):
    text = str(exc).strip() or exc.__class__.__name__
    text = " ".join(text.split())
    return text[:200]


def _cache_get(cache, key, ttl_sec):
    item = cache.get(key)
    if not item:
        return None
    if (time.time() - item["ts"]) > ttl_sec:
        cache.pop(key, None)
        return None
    return dict(item["value"])


def _cache_set(cache, key, value):
    cache[key] = {"ts": time.time(), "value": dict(value)}


def _get_bse_session():
    session = getattr(_tls, "bse_session", None)
    if session is not None:
        return session
    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bseindia.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    _tls.bse_session = session
    return session


def _to_crore(value):
    v = _safe_num(value)
    return None if v is None else v / 1e7


def _normalize_debt_to_equity(value):
    v = _safe_num(value)
    if v is None:
        return None
    return v / 100 if v > 10 else v


def _extract_number(text):
    m = re.search(r"-?\d+(\.\d+)?", text)
    return _safe_num(m.group(0)) if m else None


def _extract_metric_key(line):
    lower = line.lower()
    label = lower
    for op in (">=", "<=", ">", "<", "="):
        if op in label:
            label = label.split(op, 1)[0].strip()
            break
    if label in UNSUPPORTED_LIVE_ALIASES:
        return "__unsupported__"
    if label in PARAMETER_ALIASES:
        return PARAMETER_ALIASES[label]
    for phrase in sorted(UNSUPPORTED_LIVE_ALIASES, key=len, reverse=True):
        if phrase in lower:
            return "__unsupported__"
    for phrase in sorted(PARAMETER_ALIASES.keys(), key=len, reverse=True):
        if phrase in lower:
            return PARAMETER_ALIASES[phrase]
    return None


def _series_cagr(series, years):
    try:
        s = series.dropna()
        if len(s) <= years:
            return None
        start, end = float(s.iloc[-years]), float(s.iloc[0])
        if start <= 0:
            return None
        return ((end / start) ** (1 / years) - 1) * 100
    except Exception:
        return None


def _series_return(close_series, years):
    try:
        s = close_series.dropna()
        pts = years * 252
        if len(s) <= pts:
            return None
        start, end = float(s.iloc[-pts]), float(s.iloc[-1])
        if start <= 0:
            return None
        return ((end / start) - 1) * 100
    except Exception:
        return None


def _series_return_months(close_series, months):
    try:
        s = close_series.dropna()
        pts = int(months * 21)
        if len(s) <= pts:
            return None
        start, end = float(s.iloc[-pts]), float(s.iloc[-1])
        if start <= 0:
            return None
        return ((end / start) - 1) * 100
    except Exception:
        return None


def _worker_init_nse_session():
    from services.nse_service import get_nse_session
    _tls.nse_session = get_nse_session()


def _metrics_from_numeric_filters(numeric_filters):
    keys = set()
    for k in numeric_filters:
        if k.startswith("min_"):
            keys.add(k[4:])
        elif k.startswith("max_"):
            keys.add(k[4:])
    return keys


def _matches_numeric_filters(row, numeric_filters, pass_on_none=False):
    for k, val in numeric_filters.items():
        if val is None:
            continue
        bound, metric = k.split("_", 1)
        actual = row.get(metric)
        if actual is None:
            if pass_on_none:
                continue
            else:
                return False
        if bound == "min" and actual < val:
            return False
        if bound == "max" and actual > val:
            return False
    return True


def _parse_promoter_pct(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return None


def _get_bse_full_universe():
    cache_key = "bse_full_universe"
    cached = _cache_get(_BSE_UNIVERSE_CACHE, cache_key, _BASIC_CACHE_TTL_SEC)
    if cached:
        return cached["rows"]

    session = _get_bse_session()
    rows = session.get(
        "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w",
        params={"segment": "Equity", "status": "Active"},
        timeout=60,
    ).json()

    cleaned = []
    for row in rows:
        mktcap = _safe_num(row.get("Mktcap"))
        if mktcap is None:
            continue
        scrip_id = str(row.get("scrip_id") or "").strip()
        scrip_cd = str(row.get("SCRIP_CD") or "").strip()
        if not scrip_id or not scrip_cd:
            continue
        cleaned.append({
            "bse_code": scrip_cd,
            "symbol": scrip_id,
            "yahoo_symbol": f"{scrip_id}.NS",
            "name": row.get("Issuer_Name") or row.get("Scrip_Name") or scrip_id,
            "market_cap_cr": mktcap,
            "group": row.get("GROUP"),
        })

    cleaned.sort(key=lambda x: x["market_cap_cr"], reverse=True)
    _cache_set(_BSE_UNIVERSE_CACHE, cache_key, {"rows": cleaned})
    return cleaned


def _fetch_bse_detail_snapshot(row):
    cache_key = row["bse_code"]
    cached = _cache_get(_BSE_DETAIL_CACHE, cache_key, _BASIC_CACHE_TTL_SEC)
    if cached:
        return cached

    session = _get_bse_session()
    code = row["bse_code"]
    com, head = {}, {}

    for attempt in range(3):
        try:
            com = session.get(
                "https://api.bseindia.com/BseIndiaAPI/api/ComHeadernew/w",
                params={"quotetype": "EQ", "scripcode": code, "seriesid": ""},
                timeout=10,
            ).json()
            head = session.get(
                "https://api.bseindia.com/BseIndiaAPI/api/GetScripHeaderData/w",
                params={"pType": 1, "scripcode": code},
                timeout=10,
            ).json()
            break
        except Exception:
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))

    header = head.get("Header") or {}
    detail = {
        "symbol": row["symbol"],
        "yahoo_symbol": row["yahoo_symbol"],
        "name": row["name"],
        "bse_code": code,
        "market_cap_cr": row["market_cap_cr"],
        "market_cap": row["market_cap_cr"] * 1e7,
        "price": _safe_num(header.get("LTP")),
        "pe": _safe_num(com.get("ConPE") or com.get("PE")),
        "pb": _safe_num(com.get("ConPB") or com.get("PB")),
        "roe": _safe_num(com.get("ConROE") or com.get("ROE")),
        "eps": _safe_num(com.get("ConEPS") or com.get("EPS")),
        "opm": _safe_num(com.get("ConOPM") or com.get("OPM")),
    }
    _cache_set(_BSE_DETAIL_CACHE, cache_key, detail)
    return dict(detail)


def _get_screener_data_cached(symbol_ns):
    """Fetch Screener.in data with caching — avoids re-scraping same stock."""
    cached = _cache_get(_SCREENER_CACHE, symbol_ns, _BASIC_CACHE_TTL_SEC)
    if cached:
        return cached
    try:
        sd = fetch_screener_data(symbol_ns)
        if sd:
            _cache_set(_SCREENER_CACHE, symbol_ns, sd)
        return sd or {}
    except Exception:
        return {}


def _fetch_india_snapshot_cascade(symbol_ns, numeric_filters):
    """
    Full data cascade for Indian stocks:
    1. yfinance — baseline data
    2. NSE API — better ROE/ROCE
    3. Screener.in — PRIORITY source for ROE, D/E, PE
       (not just fallback — Screener.in data is more accurate
        for Indian stocks than yfinance)
    """
    row = _fetch_symbol_snapshot(symbol_ns)
    if not row:
        return None

    sym = symbol_ns.replace(".NS", "").upper()

    # Layer 2: NSE API for ROE/ROCE
    session = getattr(_tls, "nse_session", None)
    try:
        nse = fetch_nse_data(sym, session=session) if session else fetch_nse_data(sym)
    except Exception:
        nse = {}

    if nse.get("ROE") is not None:
        row["roe"] = float(nse["ROE"])
    if nse.get("ROCE") is not None:
        row["roce"] = float(nse["ROCE"])

    # Layer 3: Screener.in — used as PRIMARY source for key metrics
    # This is important because yfinance values for Indian stocks
    # often differ significantly from actual reported values
    active_metrics = _metrics_from_numeric_filters(numeric_filters)
    screener_relevant = {"roe", "roce", "debt_to_equity", "interest_coverage",
                         "promoter_holding", "pe"}

    # Fetch Screener.in if any of our filter metrics overlap with what it provides
    if screener_relevant.intersection(active_metrics):
        sd = _get_screener_data_cached(symbol_ns)

        # ROE — prefer Screener.in over yfinance for Indian stocks
        if sd.get("ROE") is not None:
            row["roe"] = float(sd["ROE"])

        # ROCE
        if sd.get("ROCE") is not None:
            row["roce"] = float(sd["ROCE"])

        # D/E — prefer Screener.in
        if sd.get("Debt-Equity (Screener)") is not None:
            row["debt_to_equity"] = _normalize_debt_to_equity(
                sd["Debt-Equity (Screener)"]
            )

        # Interest Coverage
        if sd.get("Interest Coverage") is not None and row.get("interest_coverage") is None:
            row["interest_coverage"] = _safe_num(sd["Interest Coverage"])

        # Promoter Holding
        if sd.get("Promoter Holding") is not None and row.get("promoter_holding") is None:
            p = _parse_promoter_pct(sd["Promoter Holding"])
            if p is not None:
                row["promoter_holding"] = p

    return row


def _fetch_symbol_snapshot(symbol):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info or {}
        financials = stock.financials
        quarterly = stock.quarterly_financials
        hist = stock.history(period="5y", interval="1d")

        revenue_series = financials.loc["Total Revenue"] if isinstance(financials, pd.DataFrame) and "Total Revenue" in financials.index else pd.Series(dtype=float)
        profit_series = financials.loc["Net Income"] if isinstance(financials, pd.DataFrame) and "Net Income" in financials.index else pd.Series(dtype=float)
        ebit_series = financials.loc["Ebit"] if isinstance(financials, pd.DataFrame) and "Ebit" in financials.index else pd.Series(dtype=float)

        q_sales_cr = q_pat_cr = q_sales_yoy = q_pat_yoy = None
        latest_results_period = None
        if isinstance(quarterly, pd.DataFrame) and not quarterly.empty:
            if len(quarterly.columns) > 0:
                latest_col = quarterly.columns[0]
                latest_results_period = latest_col.strftime("%Y-%m-%d") if hasattr(latest_col, "strftime") else str(latest_col)
            if "Total Revenue" in quarterly.index:
                qrev = quarterly.loc["Total Revenue"].dropna()
                if len(qrev) > 0:
                    q_sales_cr = _to_crore(qrev.iloc[0])
                if len(qrev) >= 5 and _safe_num(qrev.iloc[4]):
                    q_sales_yoy = ((_safe_num(qrev.iloc[0]) / _safe_num(qrev.iloc[4])) - 1) * 100
            if "Net Income" in quarterly.index:
                qpat = quarterly.loc["Net Income"].dropna()
                if len(qpat) > 0:
                    q_pat_cr = _to_crore(qpat.iloc[0])
                if len(qpat) >= 5 and _safe_num(qpat.iloc[4]):
                    q_pat_yoy = ((_safe_num(qpat.iloc[0]) / _safe_num(qpat.iloc[4])) - 1) * 100

        pe = _safe_num(info.get("trailingPE"))
        roe = _safe_num(info.get("returnOnEquity"))
        roa = _safe_num(info.get("returnOnAssets"))
        roce = _safe_num(info.get("returnOnCapital"))
        opm = None
        if len(ebit_series) and len(revenue_series):
            ebit, rev = _safe_num(ebit_series.iloc[0]), _safe_num(revenue_series.iloc[0])
            if ebit is not None and rev:
                opm = (ebit / rev) * 100

        close = hist["Close"] if isinstance(hist, pd.DataFrame) and "Close" in hist.columns else pd.Series(dtype=float)
        return {
            "symbol": symbol,
            "name": info.get("shortName") or info.get("longName") or symbol,
            "sector": info.get("sector"),
            "market_cap": _safe_num(info.get("marketCap")),
            "market_cap_cr": _to_crore(info.get("marketCap")),
            "pe": pe,
            "industry_pe": None,
            "dividend_yield": (_safe_num(info.get("dividendYield")) * 100) if info.get("dividendYield") is not None else None,
            "pb": _safe_num(info.get("priceToBook")),
            "roce": (roce * 100) if roce is not None and roce < 1 else roce,
            "roa": (roa * 100) if roa is not None else None,
            "debt_to_equity": _normalize_debt_to_equity(info.get("debtToEquity")),
            "roe": (roe * 100) if roe is not None else None,
            "eps": _safe_num(info.get("trailingEps")),
            "debt_cr": _to_crore(info.get("totalDebt")),
            "promoter_holding": (_safe_num(info.get("heldPercentInsiders")) * 100) if info.get("heldPercentInsiders") is not None else None,
            "change_promoter_holding": None,
            "earnings_yield": (100 / pe) if pe and pe > 0 else None,
            "pledged_percentage": None,
            "sales_growth_3y": _series_cagr(revenue_series, 3),
            "sales_growth_5y": _series_cagr(revenue_series, 5),
            "profit_growth_3y": _series_cagr(profit_series, 3),
            "profit_growth_5y": _series_cagr(profit_series, 5),
            "price": _safe_num(info.get("currentPrice") or info.get("regularMarketPrice")),
            "price_to_sales": _safe_num(info.get("priceToSalesTrailing12Months")),
            "price_to_fcf": _safe_num(info.get("priceToFreeCashflows")),
            "ev_ebitda": _safe_num(info.get("enterpriseToEbitda")),
            "enterprise_value_cr": _to_crore(info.get("enterpriseValue")),
            "current_ratio": _safe_num(info.get("currentRatio")),
            "interest_coverage": _safe_num(info.get("interestCoverage")),
            "peg_ratio": _safe_num(info.get("pegRatio")),
            "return_3m": _series_return_months(close, 3),
            "return_6m": _series_return_months(close, 6),
            "return_1y": _series_return(close, 1),
            "return_3y": _series_return(close, 3),
            "return_5y": _series_return(close, 5),
            "sales_cr": _to_crore(info.get("totalRevenue")),
            "pat_cr": _to_crore(info.get("netIncomeToCommon")),
            "opm": opm,
            "sales_latest_qtr_cr": q_sales_cr,
            "pat_latest_qtr_cr": q_pat_cr,
            "qtr_sales_growth_yoy": q_sales_yoy,
            "qtr_profit_growth_yoy": q_pat_yoy,
            "avg_roe_3y": (roe * 100) if roe is not None else None,
            "avg_roe_5y": (roe * 100) if roe is not None else None,
            "latest_results_period": latest_results_period,
        }
    except Exception as exc:
        return {"symbol": symbol, "_fetch_error": _clean_exception_message(exc)}


def _apply_query_filters(query, filters):
    if not query:
        return filters
    unsupported = []
    lines = [x.strip() for x in re.split(r"\n|\band\b", query, flags=re.IGNORECASE) if x.strip()]
    for line in lines:
        value = _extract_number(line)
        if value is None:
            continue
        metric = _extract_metric_key(line)
        if not metric or metric == "__unsupported__":
            if any(op in line for op in (">=", "<=", ">", "<", "=")):
                unsupported.append(line)
            continue
        if ">=" in line or ">" in line:
            filters[f"min_{metric}"] = value
        elif "<=" in line or "<" in line:
            filters[f"max_{metric}"] = value
        elif "=" in line:
            filters[f"min_{metric}"] = value
            filters[f"max_{metric}"] = value
    if unsupported:
        filters["_unsupported_filters"] = unsupported
    return filters


def _snapshot_for_symbol(symbol_ns, numeric_filters):
    try:
        if symbol_ns.endswith(".NS"):
            return _fetch_india_snapshot_cascade(symbol_ns, numeric_filters)
        return _fetch_symbol_snapshot(symbol_ns)
    except Exception as exc:
        return {"symbol": symbol_ns, "_fetch_error": _clean_exception_message(exc)}


def run_classic_screener(filters):
    filters = _apply_query_filters(filters.get("query"), dict(filters))
    numeric_filters = {
        k: _safe_num(v)
        for k, v in filters.items()
        if (k.startswith("min_") or k.startswith("max_")) and k not in _SCREENER_PAYLOAD_KEYS
    }
    limit = int(filters.get("limit", 30) or 30)
    market = (filters.get("market") or "all").lower()
    require_dec_results = bool(filters.get("require_dec_results"))
    workers = min(8, max(2, int(filters.get("parallel_workers", 4) or 4)))

    screen_meta = {
        "universe": "unknown",
        "symbol_count": 0,
        "parallel_workers": workers,
        "require_dec_results": require_dec_results,
    }
    unsupported_filters = filters.get("_unsupported_filters") or []
    if unsupported_filters:
        screen_meta["unsupported_filters"] = unsupported_filters
        screen_meta["matches_returned"] = 0
        screen_meta["matches_before_limit"] = 0
        return {"results": [], "count": 0, "meta": screen_meta}

    fetch_failures = []

    if market == "india":
        all_bse_rows = _get_bse_full_universe()
        screen_meta["total_bse_stocks"] = len(all_bse_rows)
        screen_meta["universe"] = "bse_all_active_equity"

        mcap_min = numeric_filters.get("min_market_cap_cr")
        mcap_max = numeric_filters.get("max_market_cap_cr")

        mcap_filtered = []
        for row in all_bse_rows:
            mc = row.get("market_cap_cr")
            if mc is None:
                continue
            if mcap_min is not None and mc < mcap_min:
                continue
            if mcap_max is not None and mc > mcap_max:
                continue
            mcap_filtered.append(row)

        screen_meta["after_mcap_filter"] = len(mcap_filtered)

        stage1_filter_keys = {
            k: v for k, v in numeric_filters.items()
            if k.split("_", 1)[1] in BSE_STAGE1_METRICS
        }
        remaining_filter_keys = {
            k: v for k, v in numeric_filters.items()
            if k.split("_", 1)[1] not in BSE_STAGE1_METRICS
        }

        stage1_workers = min(10, max(4, workers * 2))
        stage1_rows = []

        with ThreadPoolExecutor(max_workers=stage1_workers) as executor:
            futures = [executor.submit(_fetch_bse_detail_snapshot, row) for row in mcap_filtered]
            for future in as_completed(futures):
                try:
                    row = future.result()
                    stage1_rows.append(row)
                except Exception as exc:
                    fetch_failures.append({
                        "symbol": "BSE_DETAIL",
                        "error": _clean_exception_message(exc),
                    })

        # Stage 1 uses pass_on_none=True — stocks with missing BSE data
        # pass through to Stage 2 (yfinance + Screener) instead of being dropped
        stage1_candidates = [
            row for row in stage1_rows
            if _matches_numeric_filters(row, stage1_filter_keys, pass_on_none=True)
        ]

        screen_meta["bse_detail_fetched"] = len(stage1_rows)
        screen_meta["basic_prefilter_metrics"] = sorted(_metrics_from_numeric_filters(stage1_filter_keys))
        screen_meta["basic_prefilter_candidates"] = len(stage1_candidates)

        # All candidates go to Stage 2 for accurate Screener.in data
        stage2_universe = [row["yahoo_symbol"] for row in stage1_candidates]
        screen_meta["deep_fetch_candidates"] = len(stage2_universe)
        screen_meta["symbol_count"] = len(mcap_filtered)

        pool_kw = {"max_workers": workers, "initializer": _worker_init_nse_session}
        results = []

        with ThreadPoolExecutor(**pool_kw) as executor:
            futures = [executor.submit(_snapshot_for_symbol, sym, numeric_filters) for sym in stage2_universe]
            for future in as_completed(futures):
                row = future.result()
                if not row:
                    continue
                if row.get("_fetch_error"):
                    fetch_failures.append({
                        "symbol": row.get("symbol"),
                        "error": row["_fetch_error"],
                    })
                    continue
                if require_dec_results:
                    latest_period = str(row.get("latest_results_period") or "")
                    if not latest_period.startswith("2025-12"):
                        continue
                if _matches_numeric_filters(row, numeric_filters, pass_on_none=False):
                    results.append(row)

        results.sort(key=lambda x: (x.get("roe") is None, -(x.get("roe") or 0)))
        trimmed = results[:max(1, min(limit, 100))]
        screen_meta["symbols_fully_evaluated"] = len(stage2_universe)
        screen_meta["matches_returned"] = len(trimmed)
        screen_meta["matches_before_limit"] = len(results)
        screen_meta["fetch_failures"] = len(fetch_failures)
        screen_meta["fetch_successes"] = max(0, len(stage2_universe) - len(fetch_failures))
        return {"results": trimmed, "meta": screen_meta}

    elif market in ("us", "newyork"):
        universe = list(DEFAULT_US_UNIVERSE)
        screen_meta["universe"] = "builtin_sample_us"
        screen_meta["symbol_count"] = len(universe)
    else:
        universe = list(DEFAULT_INDIAN_UNIVERSE) + list(DEFAULT_US_UNIVERSE)
        screen_meta["universe"] = "builtin_sample_india_us"
        screen_meta["symbol_count"] = len(universe)

    pool_kw = {"max_workers": workers}
    results = []

    with ThreadPoolExecutor(**pool_kw) as executor:
        futures = [executor.submit(_snapshot_for_symbol, sym, numeric_filters) for sym in universe]
        for future in as_completed(futures):
            row = future.result()
            if not row or row.get("_fetch_error"):
                if row:
                    fetch_failures.append({"symbol": row.get("symbol"), "error": row["_fetch_error"]})
                continue
            if _matches_numeric_filters(row, numeric_filters, pass_on_none=False):
                results.append(row)

    results.sort(key=lambda x: (x.get("roe") is None, -(x.get("roe") or 0)))
    trimmed = results[:max(1, min(limit, 100))]
    screen_meta["matches_returned"] = len(trimmed)
    screen_meta["fetch_failures"] = len(fetch_failures)
    return {"results": trimmed, "meta": screen_meta}
