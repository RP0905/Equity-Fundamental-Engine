
from app import run_google_sheets_screener

# Test with Multibagger query
filters = {
    "query": """Sales Growth > 15
Profit Growth > 20
Return on Capital Employed > 20
Debt to Equity < 0.5
Promoter Holding > 50
Pledged Percentage = 0
Market Capitalization < 50000
Cash Flow From Operating > 0""",
    "limit": 50,
    "use_local_db": False
}
result = run_google_sheets_screener(filters)
print("Result keys:", list(result.keys()))
print("Count:", result.get("count"))
print("Results length:", len(result.get("results", [])))
for res in result.get("results", []):
    print("-", res["name"], res["symbol"])

