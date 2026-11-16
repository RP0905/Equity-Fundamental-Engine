import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix price-history
content = re.sub(
    r'(if yf_symbol is None:\s*)if not symbol\.endswith\("\.NS"\) and not symbol\.endswith\("\.BO"\):\s*symbol \+= "\.NS"\s*yf_symbol = symbol',
    r'\1yf_symbol = symbol',
    content
)

# Fix peers check 1
content = re.sub(
    r'(if not symbol:\s*return jsonify\({"error": "symbol required"}\), 400\s*)if not symbol\.endswith\("\.NS"\):\s*symbol \+= "\.NS"\s*',
    r'\1',
    content
)

# Fix peers check 2
content = re.sub(
    r'(ps_str = ps\.strip\(\)\.upper\(\)\s*)if not ps_str\.endswith\("\.NS"\):\s*ps_str \+= "\.NS"\s*',
    r'\1',
    content
)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Applied fixes to app.py")
