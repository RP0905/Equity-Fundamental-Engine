from pathlib import Path
import os
import threading

import yfinance as yf

_lock = threading.Lock()
_configured = False


def _disable_broken_loopback_proxies():
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    ):
        value = os.environ.get(key)
        if not value:
            continue

        lower = value.lower()
        if "127.0.0.1:9" in lower or "localhost:9" in lower:
            os.environ.pop(key, None)


def configure_yfinance_cache():
    global _configured

    if _configured:
        return

    with _lock:
        if _configured:
            return

        _disable_broken_loopback_proxies()

        cache_dir = Path(__file__).resolve().parents[1] / ".cache" / "yfinance"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # yfinance stores timezone and cookie caches in SQLite files.
        # Point them into the project so they remain writable in this environment.
        yf.set_tz_cache_location(str(cache_dir))
        _configured = True
