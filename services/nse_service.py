import requests
import time

# NSE requires browser-like headers + a session cookie
def get_nse_session():
    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com/",
        "Connection": "keep-alive",
    })
    # Hit homepage first to get session cookie
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
    except:
        pass
    return session


def get_shareholding(symbol):
    """Fetch promoter/FII/DII/public holding from NSE"""
    try:
        session = get_nse_session()
        url = f"https://www.nseindia.com/api/corporate-shareholding-patterns?index=equities&symbol={symbol}"
        res = session.get(url, timeout=10)

        if res.status_code != 200:
            return None

        data = res.json()
        if not data or "data" not in data or len(data["data"]) == 0:
            return None

        # Get most recent quarter
        latest = data["data"][0]

        result = {
            "period": latest.get("date", ""),
            "promoter": None,
            "fii": None,
            "dii": None,
            "public": None,
        }

        for item in latest.get("shareholdingPatterns", {}).get("data", []):
            name = item.get("category", "").lower()
            pct = item.get("holdingPercentage")

            if "promoter" in name:
                result["promoter"] = pct
            elif "foreign" in name or "fii" in name or "fpi" in name:
                result["fii"] = pct
            elif "domestic" in name or "dii" in name or "institution" in name:
                result["dii"] = pct
            elif "public" in name or "retail" in name:
                result["public"] = pct

        return result

    except Exception as e:
        return None


def get_nse_peers(symbol):
    """Fetch peer companies from NSE"""
    try:
        session = get_nse_session()
        url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        res = session.get(url, timeout=10)

        if res.status_code != 200:
            return []

        data = res.json()
        peers = []

        # NSE gives industry peers in metadata
        industry = data.get("metadata", {}).get("industry", "")
        series = data.get("metadata", {}).get("series", "EQ")

        if industry:
            url2 = f"https://www.nseindia.com/api/live-analysis-variations?index=gainers"
            # Use screener fallback for peers
            pass

        return []

    except:
        return []
