"""Load NSE mainboard (EQ) symbols from the official equity list CSV."""
import io
import time

import pandas as pd
import requests

EQUITY_L_CSV_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
}

_CACHE = {"symbols_ns": None, "fetched_at": 0.0}
_CACHE_TTL_SEC = 6 * 3600


def get_nse_eq_symbols_ns(ttl_sec=_CACHE_TTL_SEC):
    """
    Return Yahoo-style tickers for NSE EQ series (mainboard), e.g. RELIANCE.NS.
    Cached in-process for ttl_sec to avoid hammering NSE archives.
    """
    now = time.time()
    if _CACHE["symbols_ns"] and (now - _CACHE["fetched_at"]) < ttl_sec:
        return _CACHE["symbols_ns"]

    session = requests.Session()
    session.trust_env = False
    res = session.get(EQUITY_L_CSV_URL, headers=HEADERS, timeout=120)
    res.raise_for_status()
    df = pd.read_csv(io.BytesIO(res.content))
    df.columns = [str(c).strip() for c in df.columns]
    if "SERIES" not in df.columns or "SYMBOL" not in df.columns:
        raise ValueError("Unexpected EQUITY_L.csv schema")

    df = df[df["SERIES"].astype(str).str.strip().str.upper() == "EQ"]
    symbols = (df["SYMBOL"].astype(str).str.strip() + ".NS").tolist()

    _CACHE["symbols_ns"] = symbols
    _CACHE["fetched_at"] = now
    return symbols
