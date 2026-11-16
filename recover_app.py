import json
import os
import re

transcript_path = r"C:\Users\ROHEET\.gemini\antigravity-ide\brain\f875c790-3a18-4b8b-99cc-9ee893eb94ab\.system_generated\logs\transcript_full.jsonl"
app_content = []

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content", "")
            if "File Path:" in content and "app.py" in content:
                # view_file outputs lines like '240:     if not symbol:'
                # We can extract them
                app_content.append(content)
        except Exception as e:
            pass
            
with open("recovered_fragments.txt", "w", encoding="utf-8") as f:
    for block in app_content:
        f.write(block)
        f.write("\n" + "="*50 + "\n")
