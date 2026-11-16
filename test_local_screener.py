
from services.screener_local_service import run_local_screener

# Test with empty filters
filters = {"query": "", "limit": 5, "use_local_db": True}
result = run_local_screener(filters)
print("Result keys:", list(result.keys()))
print("Count:", result.get("count"))
print("Results length:", len(result.get("results", [])))
print("Results:", result.get("results", []))

