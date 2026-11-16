from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
import json
import math
from pathlib import Path
import re
import sys

from app import _compare_metric, _latest, _metric_lookup, _normalize_filter_label, run_google_sheets_screener
from services.google_sheets_service import (
    _calculate_fundamentals,
    _load_workbook,
    _parse_data_sheet,
    _parse_profit_loss_sheet,
    load_master_index,
)


PRESET_QUERIES = {
    "Multibagger": """Sales Growth > 15
Profit Growth > 20
Return on Capital Employed > 20
Debt to Equity < 0.5
Promoter Holding > 50
Market Capitalization < 50000""",
    "Placeholder Example": "Market Capitalization > 10000 AND Return on Equity > 15",
}


RATIO_LABELS = [
    "Market Capitalization", "Market Cap", "Price to Earning", "P/E",
    "Price to Book Value", "P/B", "Price to Sales", "P/S",
    "Price to Free Cash Flow", "P/FCF", "EV/EBITDA", "Enterprise Value",
    "EV", "Earnings Yield", "Dividend Yield", "Return on Equity", "ROE",
    "Return on Capital Employed", "ROCE", "Return on Assets", "ROA",
    "Net Profit Margin", "Operating Profit Margin", "Gross Profit Margin",
    "EBITDA Margin", "Earnings Per Share", "EPS", "Book Value Per Share",
    "BVPS", "Dividend Per Share", "DPS", "Debt", "Total Debt",
    "Debt to Equity", "D/E", "Interest Coverage Ratio", "Current Ratio",
    "Quick Ratio", "Cash Ratio", "Promoter Holding", "FII Holding",
    "DII Holding", "Public Holding", "Pledged Percentage", "Sales",
    "Revenue", "Profit After Tax", "PAT", "Operating Profit", "EBITDA",
    "Gross Profit", "Profit Before Tax", "PBT", "Sales Latest Quarter",
    "Profit After Tax Latest Quarter", "YoY Quarterly Sales Growth",
    "YoY Quarterly Profit Growth", "QoQ Quarterly Sales Growth",
    "QoQ Quarterly Profit Growth", "Sales Growth", "Sales Growth 3Years",
    "Sales Growth 5Years", "Profit Growth", "Profit Growth 3Years",
    "Profit Growth 5Years", "Revenue Growth", "Revenue Growth 3Years",
    "Revenue Growth 5Years", "Earnings Growth", "Earnings Growth 3Years",
    "Earnings Growth 5Years", "Current Price", "Price", "52 Week High",
    "52 Week Low", "52 Week Change", "Volume", "Average Volume", "Beta",
    "RSI", "MACD", "Cash Flow From Operating", "Cash Flow From Investing",
    "Cash Flow From Financing", "Free Cash Flow", "FCF",
    "Cash and Cash Equivalents", "Total Assets", "Total Liabilities",
    "Shareholders Equity", "Reserves", "Inventory", "Accounts Receivable",
    "Accounts Payable", "Asset Turnover", "Inventory Turnover",
    "Receivables Turnover", "Working Capital", "Working Capital Turnover",
    "Payout Ratio", "Dividend Payout Ratio", "Dividend Growth Rate",
    "Average Return on Equity 3Years", "Average ROE 3Years",
    "Average Return on Equity 5Years", "Average ROE 5Years",
]


def metrics_for_entry(entry):
    workbook = _load_workbook(entry["sheet_id"])
    data_sheet = _parse_data_sheet(workbook["Data Sheet"])
    _, pnl_rows = _parse_profit_loss_sheet(workbook["Profit & Loss"])
    calculated = _calculate_fundamentals(data_sheet, pnl_rows)

    metrics = {
        "market capitalization": data_sheet["market_cap_cr"],
        "market cap": data_sheet["market_cap_cr"],
        "current price": data_sheet["current_price"],
        "price": data_sheet["current_price"],
        "roe": _latest(calculated["roe"]),
        "return on equity": _latest(calculated["roe"]),
        "roce": _latest(calculated["roce"]),
        "return on capital employed": _latest(calculated["roce"]),
        "net margin": _latest(calculated["net_margin"]),
        "net profit margin": _latest(calculated["net_margin"]),
        "operating margin": _latest(calculated["operating_margin"]),
        "opm": _latest(calculated["operating_margin"]),
        "debt to equity": _latest(calculated["debt_to_equity"]),
        "debt/equity": _latest(calculated["debt_to_equity"]),
        "d/e": _latest(calculated["debt_to_equity"]),
        "interest coverage": _latest(calculated["interest_coverage"]),
        "interest coverage ratio": _latest(calculated["interest_coverage"]),
        "sales growth 3y": calculated["revenue_cagr_3y"],
        "sales growth 3years": calculated["revenue_cagr_3y"],
        "sales growth 5y": calculated["revenue_cagr_5y"],
        "sales growth 5years": calculated["revenue_cagr_5y"],
        "profit growth 3y": calculated["profit_cagr_3y"],
        "profit growth 3years": calculated["profit_cagr_3y"],
        "profit growth 5y": calculated["profit_cagr_5y"],
        "profit growth 5years": calculated["profit_cagr_5y"],
        "revenue growth 3y": calculated["revenue_cagr_3y"],
        "revenue growth 3years": calculated["revenue_cagr_3y"],
        "revenue growth 5y": calculated["revenue_cagr_5y"],
        "revenue growth 5years": calculated["revenue_cagr_5y"],
        "sales growth": calculated["revenue_cagr_3y"],
        "profit growth": calculated["profit_cagr_3y"],
        "eps": _latest(calculated["eps"]),
        "earnings per share": _latest(calculated["eps"]),
        "book value per share": _latest(calculated["book_value_per_share"]),
        "bvps": _latest(calculated["book_value_per_share"]),
        "sales": _latest(calculated["sales"]),
        "revenue": _latest(calculated["sales"]),
        "net profit": _latest(calculated["net_profit"]),
        "profit after tax": _latest(calculated["net_profit"]),
        "pat": _latest(calculated["net_profit"]),
        "operating profit": _latest(calculated["operating_profit"]),
        "ebitda": _latest(calculated["operating_profit"]),
        "total assets": _latest(calculated["total_assets"]),
        "borrowings": _latest(calculated["borrowings"]),
        "debt": _latest(calculated["borrowings"]),
        "total debt": _latest(calculated["borrowings"]),
        "cfo": _latest(calculated["cfo"]),
        "cash from operations": _latest(calculated["cfo"]),
        "cash flow from operating": _latest(calculated["cfo"]),
        "fcf": _latest(calculated["fcf"]),
        "free cash flow": _latest(calculated["fcf"]),
        "promoter holding": data_sheet.get("promoter_holding"),
        "pledged percentage": data_sheet.get("pledged_percentage", 0),
    }
    latest_eps = _latest(calculated["eps"])
    latest_bvps = _latest(calculated["book_value_per_share"])
    if data_sheet["current_price"] and latest_eps and latest_eps > 0:
        pe = data_sheet["current_price"] / latest_eps
        metrics.update({"pe": pe, "price to earning": pe, "price to earnings": pe, "p/e": pe})
    if data_sheet["current_price"] and latest_bvps and latest_bvps > 0:
        pb = data_sheet["current_price"] / latest_bvps
        metrics.update({"pb": pb, "price to book": pb, "price to book value": pb, "p/b": pb})
    return {
        "symbol": entry["name"].replace(" ", ""),
        "name": entry["name"],
        "metrics": {key: json_safe(value) for key, value in metrics.items()},
    }


def json_safe(value):
    try:
        if value is None:
            return None
        value = float(value)
        if not math.isfinite(value):
            return None
        return value
    except (TypeError, ValueError):
        return None


def parse_rules(query):
    rules = []
    for line in [part.strip() for part in re.split(r"\n|\band\b", query, flags=re.IGNORECASE) if part.strip()]:
        op = next((candidate for candidate in (">=", "<=", ">", "<", "=") if candidate in line), None)
        if not op:
            continue
        label, value = line.split(op, 1)
        rules.append({"label": _normalize_filter_label(label), "operator": op, "value": float(value.strip())})
    return rules


def load_metric_cache(path):
    if not path.exists():
        return {}
    rows = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            rows[row["name"]] = row
    return rows


def write_metric_cache_row(path, row):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", default="all", help="'all' or number of master-index entries to audit")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--cache", default="screener_metric_cache.jsonl")
    parser.add_argument("--output", default="screener_query_audit_full.json")
    args = parser.parse_args()

    all_entries = load_master_index()
    limit = len(all_entries) if str(args.limit).lower() == "all" else int(args.limit)
    entries = all_entries[:limit]
    cache_path = Path(args.cache)
    cached = load_metric_cache(cache_path)

    rows = []
    errors = []
    pending = []
    for entry in entries:
        if entry["name"] in cached:
            rows.append(cached[entry["name"]])
        else:
            pending.append(entry)

    print(f"Loaded {len(rows)} cached metric rows; fetching {len(pending)} of {len(entries)}.", file=sys.stderr)
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(metrics_for_entry, entry): entry for entry in pending}
        for future in as_completed(futures):
            entry = futures[future]
            try:
                row = future.result()
                rows.append(row)
                write_metric_cache_row(cache_path, row)
            except Exception as exc:
                errors.append({"name": entry["name"], "error": str(exc)})
            completed += 1
            if completed % 25 == 0:
                print(f"Fetched {completed}/{len(pending)} pending rows; total usable rows {len(rows)}.", file=sys.stderr)

    ratio_support = []
    for label in RATIO_LABELS:
        key = _normalize_filter_label(label)
        available = 0
        sample_values = []
        resolved_key = None
        for row in rows:
            resolved, value = _metric_lookup(row["metrics"], key)
            resolved_key = resolved_key or resolved
            if value is not None:
                available += 1
                if len(sample_values) < 3:
                    sample_values.append({"name": row["name"], "value": value})
        ratio_support.append({
            "label": label,
            "status": "working" if available else "not_mapped_or_no_data",
            "available_in_sample": available,
            "sample_size": len(rows),
            "resolved_key": resolved_key,
            "sample_values": sample_values,
        })

    query_reports = []
    for name, query in PRESET_QUERIES.items():
        rules = parse_rules(query)
        manual_matches = []
        missing_metric_counts = {}
        rule_fail_counts = {}
        for row in rows:
            passed = True
            checked = {}
            for rule in rules:
                key, value = _metric_lookup(row["metrics"], rule["label"])
                checked[key] = value
                if value is None:
                    missing_metric_counts[key] = missing_metric_counts.get(key, 0) + 1
                    passed = False
                    break
                if not _compare_metric(value, rule["operator"], rule["value"]):
                    rule_fail_counts[key] = rule_fail_counts.get(key, 0) + 1
                    passed = False
                    break
            if passed:
                manual_matches.append({"name": row["name"], "symbol": row["symbol"], "checked": checked})
        api_result = None
        if limit <= 100:
            with redirect_stdout(sys.stderr):
                api_result = run_google_sheets_screener({
                    "query": query,
                    "limit": 50,
                    "max_symbols": limit,
                    "use_local_db": False,
                })
        api_names = {item["name"] for item in api_result["results"]} if api_result else set()
        manual_names = {item["name"] for item in manual_matches}
        query_reports.append({
            "name": name,
            "query": query,
            "api_count": api_result["count"] if api_result else None,
            "manual_count": len(manual_matches),
            "api_results": [item["name"] for item in api_result["results"]] if api_result else [],
            "manual_results": [item["name"] for item in manual_matches],
            "status": "working_full_universe" if manual_matches else "working_but_no_matches",
            "missing_from_api": sorted(manual_names - api_names),
            "extra_in_api": sorted(api_names - manual_names),
            "meta": api_result["meta"] if api_result else {
                "source": "independent_full_spreadsheet_audit",
                "symbols_evaluated": len(rows),
                "missing_metric_counts": missing_metric_counts,
                "rule_fail_counts": rule_fail_counts,
                "note": "Skipped run_google_sheets_screener API comparison because app currently caps max_symbols at 100.",
            },
        })

    report = {
        "sample_size": len(rows),
        "master_index_count": len(all_entries),
        "requested_count": len(entries),
        "load_errors": errors,
        "preset_queries": query_reports,
        "ratio_support": ratio_support,
    }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
