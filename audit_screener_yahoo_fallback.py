from __future__ import annotations

import csv
import json
from pathlib import Path

import app
from audit_screener_queries import PRESET_QUERIES, RATIO_LABELS
from services.google_sheets_service import load_master_index


SENTINEL_MIN = -1_000_000_000_000_000_000


def parse_preset_query(query: str):
    rules = []
    for raw_part in query.replace("\r", "\n").split("\n"):
        for part in raw_part.split(" AND "):
            line = part.strip()
            if not line:
                continue
            op = next((candidate for candidate in (">=", "<=", ">", "<", "=") if candidate in line), None)
            if not op:
                continue
            label, value = line.split(op, 1)
            rules.append(
                {
                    "label": app._normalize_filter_label(label),
                    "operator": op,
                    "value": float(value.strip()),
                }
            )
    return rules


def audit_ratio_support(rows):
    support = []
    total = len(rows)
    for index, label in enumerate(RATIO_LABELS, start=1):
        normalized = app._normalize_filter_label(label)
        rules = [{"label": normalized, "operator": ">", "value": SENTINEL_MIN}]
        results, missing, failures, fills, yahoo_misses = app._screen_cached_metric_rows(
            rows,
            rules,
            strict_missing_metrics=True,
            use_yahoo_fallback=True,
        )
        missing_count = int(missing.get(normalized, 0))
        available_count = total - missing_count
        if missing_count == 0:
            status = "perfect"
        elif available_count > 0:
            status = "partial_missing"
        else:
            status = "not_available"
        support.append(
            {
                "label": label,
                "normalized_label": normalized,
                "status": status,
                "master_index_count": total,
                "available_after_yahoo": available_count,
                "missing_after_yahoo": missing_count,
                "matches_for_broad_test": len(results),
                "failed_broad_test": int(failures.get(normalized, 0)),
                "filled_from_yahoo": int(fills.get(normalized, 0)),
                "still_missing_from_yahoo": int(yahoo_misses.get(normalized, 0)),
            }
        )
        print(f"[{index}/{len(RATIO_LABELS)}] {label}: {status} ({available_count}/{total})")
    return support


def audit_presets(rows):
    preset_results = []
    for name, query in PRESET_QUERIES.items():
        rules = parse_preset_query(query)
        results, missing, failures, fills, yahoo_misses = app._screen_cached_metric_rows(
            rows,
            rules,
            strict_missing_metrics=True,
            use_yahoo_fallback=True,
        )
        preset_results.append(
            {
                "query_name": name,
                "rules": rules,
                "result_count": len(results),
                "results": [row.get("name") or row.get("symbol") for row in results],
                "missing_metric_counts": dict(missing),
                "rule_fail_counts": dict(failures),
                "yahoo_fill_counts": dict(fills),
                "yahoo_miss_counts": dict(yahoo_misses),
            }
        )
        print(f"[preset] {name}: {len(results)} matches")
    return preset_results


def write_csv(path: Path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    master_index = load_master_index()
    rows = app._load_spreadsheet_metric_cache(master_index)
    print(f"Loaded {len(rows)} spreadsheet metric rows from master index.")

    support = audit_ratio_support(rows)
    presets = audit_presets(rows)

    payload = {
        "master_index_count": len(master_index),
        "spreadsheet_metric_rows": len(rows),
        "yahoo_cache_path": str(app.YAHOO_METRIC_CACHE_PATH),
        "ratio_support": support,
        "preset_queries": presets,
    }
    json_path = Path("screener_yahoo_fallback_audit_full.json")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    write_csv(
        Path("screener_ratio_support_yahoo_fallback_full.csv"),
        support,
        [
            "label",
            "normalized_label",
            "status",
            "master_index_count",
            "available_after_yahoo",
            "missing_after_yahoo",
            "matches_for_broad_test",
            "failed_broad_test",
            "filled_from_yahoo",
            "still_missing_from_yahoo",
        ],
    )
    preset_rows = [
        {
            "query_name": row["query_name"],
            "result_count": row["result_count"],
            "missing_metric_counts": json.dumps(row["missing_metric_counts"], ensure_ascii=False),
            "rule_fail_counts": json.dumps(row["rule_fail_counts"], ensure_ascii=False),
            "yahoo_fill_counts": json.dumps(row["yahoo_fill_counts"], ensure_ascii=False),
            "yahoo_miss_counts": json.dumps(row["yahoo_miss_counts"], ensure_ascii=False),
            "results": json.dumps(row["results"], ensure_ascii=False),
        }
        for row in presets
    ]
    write_csv(
        Path("screener_preset_query_yahoo_fallback_full.csv"),
        preset_rows,
        [
            "query_name",
            "result_count",
            "missing_metric_counts",
            "rule_fail_counts",
            "yahoo_fill_counts",
            "yahoo_miss_counts",
            "results",
        ],
    )
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
