
from app import run_google_sheets_screener

# Test with empty filters
filters = {"query": "", "limit": 5, "use_local_db": False}
result = run_google_sheets_screener(filters)
print("Result keys:", list(result.keys()))
print("Count:", result.get("count"))
print("Results length:", len(result.get("results", [])))
print("Results:", result.get("results", []))

