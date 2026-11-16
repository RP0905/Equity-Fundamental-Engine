import json
import os
import re

transcript_path = r"C:\Users\ROHEET\.gemini\antigravity-ide\brain\f875c790-3a18-4b8b-99cc-9ee893eb94ab\.system_generated\logs\transcript_full.jsonl"
app_content_lines = {}

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content", "")
            if "file:///c:/Users/ROHEET/Desktop/EquityFundamentalEngine%20-%20Original/app.py" in content or "app.py" in content:
                # view_file outputs lines like '240:     if not symbol:'
                for content_line in content.split('\n'):
                    m = re.match(r'^(\d+):\s(.*)', content_line)
                    if m:
                        lineno = int(m.group(1))
                        app_content_lines[lineno] = m.group(2)
        except:
            pass

print(f"Recovered {len(app_content_lines)} unique lines out of max {max(app_content_lines.keys()) if app_content_lines else 0}.")

# fill in missing lines with '# MISSING LINE'
if app_content_lines:
    max_line = max(app_content_lines.keys())
    with open("recovered_full_app.py", "w", encoding="utf-8") as f:
        for i in range(1, max_line + 1):
            f.write(app_content_lines.get(i, f"# MISSING LINE {i}") + "\n")
