import os
import glob
import re
import datetime

history_dir = os.path.expandvars(r"%APPDATA%\Code\User\History")
found_files = []

for root, _, files in os.walk(history_dir):
    for f in files:
        path = os.path.join(root, f)
        try:
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
                if "def price_history():" in content and "def analyze():" in content:
                    found_files.append((path, len(content), os.path.getmtime(path)))
        except:
            pass

found_files.sort(key=lambda x: x[2], reverse=True)
print(f"Found {len(found_files)} candidates.")
for p, size, mtime in found_files[:5]:
    print(f"{p}: {size} bytes, modified {datetime.datetime.fromtimestamp(mtime)}")
