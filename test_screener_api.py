import requests

API_URL = "http://127.0.0.1:5000/api/screener"

print("Testing screener API with query 'Market Capitalization > 1000'...")

response = requests.post(API_URL, json={
    "query": "Market Capitalization > 1000",
    "limit": 10,
    "market": "india",
    "use_local_db": True
})

print(f"Response status: {response.status_code}")
print("Response JSON:")
import json
print(json.dumps(response.json(), indent=2))
