"""The checks that make a parsed statement a reconciled one."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Dict, List

SEVERITY_WEIGHT = {"high": 20, "medium": 8, "low": 2}

CATEGORY_RULES = [
    ("Income", ["payroll", "salary", "deposit", "refund", "interest credit", "transfer in"]),
    ("Groceries", ["whole foods", "safeway", "trader joe", "kroger", "aldi", "market", "grocer"]),
    ("Dining", ["coffee", "starbucks", "restaurant", "cafe", "pizza", "doordash", "ubereats"]),
    ("Transport", ["uber", "lyft", "shell", "chevron", "fuel", "parking", "transit", "metro"]),
    ("Subscriptions", ["netflix", "spotify", "adobe", "icloud", "github", "notion", "subscription"]),
    ("Shopping", ["amazon", "target", "walmart", "costco", "apple.com", "shop"]),
    ("Utilities", ["electric", "water", "gas bill", "internet", "comcast", "at&t", "verizon"]),
    ("Fees", ["fee", "charge", "atm", "overdraft", "interest charge"]),
    ("Housing", ["rent", "mortgage", "hoa", "insurance"]),
    ("Transfers", ["transfer", "payment - thank", "autopay", "credit card pmt"]),
]


def category_of(description: str) -> str:
    low = description.lower()
    for name, keywords in CATEGORY_RULES:
        if any(k in low for k in keywords):
            return name
    return "Other"


def _finding(check: str, severity: str, where: str, detail: str) -> Dict:
    return {"check": check, "severity": severity, "where": where, "detail": detail,
            "weight": SEVERITY_WEIGHT[severity]}


def check_balance(breaks: List[Dict]) -> List[Dict]:
    out = []
    for brk in breaks:
        out.append(_finding("balance_break", "high",
                            f"{brk['source']} · {brk['date']}",
                            f"{brk['description']}: balance should be {brk['expected']:,.2f}, "
                            f"statement says {brk['actual']:,.2f} (off by {brk['delta']:+,.2f})"))
    return out


def check_duplicates(transactions: List[Dict]) -> List[Dict]:
    keyed = defaultdict(list)
    for txn in transactions:
        keyed[(str(txn["date"]), round(txn["amount"], 2), txn["description"].strip().lower())].append(txn)
    out = []
    for key, rows in keyed.items():
        if len(rows) > 1:
            files = sorted({r["source"] for r in rows})
            out.append(_finding("duplicate_transaction", "high", f"{key[0]} · {rows[0]['description'][:40]}",
                                f"{len(rows)} identical rows, amount {key[1]:,.2f}"
                                f" (files: {', '.join(files)})"))
    return out


def check_periods(periods: List[tuple]) -> List[Dict]:
    if not periods:
        return []
    ordered = sorted(periods)
    out = []
    for i in range(1, len(ordered)):
        prev_end, cur_start = ordered[i - 1][1], ordered[i][0]
        gap = (cur_start - prev_end).days
        if gap > 3:
            out.append(_finding("period_gap", "medium" if gap <= 10 else "high", "<statements>",
                                f"{gap} days between {prev_end} and {cur_start} "
                                f"— transactions in that window are missing"))
    overlap = [i for i in range(1, len(ordered)) if ordered[i][0] < ordered[i - 1][1]]
    if overlap:
        out.append(_finding("period_overlap", "low", "<statements>",
                            f"{len(overlap)} statement period(s) overlap — de-duplicate before analysis"))
    return out


def check_totals(parsed: Dict, transactions: List[Dict]) -> List[Dict]:
    out = []
    for one in parsed.get("files_data", []):
        opening, closing = one["opening"], one["closing"]
        if opening is None or closing is None:
            continue
        net = one["totals"]["net"]
        expected = round(opening + net, 2)
        if abs(expected - closing) > 0.01:
            out.append(_finding("totals_mismatch", "medium", one["name"],
                                f"opening {opening:,.2f} + movements {net:,.2f} = "
                                f"{expected:,.2f}, statement closes at {closing:,.2f}"))
    missing = sum(1 for t in transactions if t.get("balance") is None)
    if missing:
        out.append(_finding("missing_balance_column", "medium", "<statement>",
                            f"{missing} rows carry no running balance — the chain cannot be verified"))
    return out


def check_unparsed(unparsed: List[str], transactions: List[Dict]) -> List[Dict]:
    if not unparsed:
        return []
    total = len(unparsed) + len(transactions)
    share = len(unparsed) / max(total, 1)
    severity = "high" if share > 0.2 else "medium" if share > 0.05 else "low"
    sample = "; ".join(u[:60] for u in unparsed[:2])
    return [_finding("unparsed_rows", severity, "<extraction>",
                     f"{len(unparsed)} of {total} transaction-shaped lines were not parsed "
                     f"({share:.0%}) — sample: {sample}")]


def check_hygiene(transactions: List[Dict]) -> List[Dict]:
    out = []
    zeros = [t for t in transactions if abs(t["amount"]) < 1e-9]
    if zeros:
        out.append(_finding("zero_amount", "low", "<statement>",
                            f"{len(zeros)} row(s) with a 0.00 amount"))
    inferred = [t for t in transactions if t.get("sign_inferred")]
    if inferred:
        out.append(_finding("sign_inferred", "low", "<statement>",
                            f"{len(inferred)} amount(s) had no sign and were inferred from the balance column"))
    future = [t for t in transactions if t["date"] and t["date"] > date.today()]
    if future:
        out.append(_finding("future_dated", "medium", "<statement>",
                            f"{len(future)} transaction(s) dated in the future"))
    return out


CHECKS = [
    ("balance_break", "Balance chain breaks", "high"),
    ("duplicate_transaction", "Duplicate transactions", "high"),
    ("period_gap", "Gaps between statements", "medium"),
    ("totals_mismatch", "Opening + movements ≠ closing", "medium"),
    ("missing_balance_column", "No running balance", "medium"),
    ("unparsed_rows", "Rows that failed to parse", "medium"),
    ("sign_inferred", "Signs inferred from balance", "low"),
    ("zero_amount", "Zero amounts", "low"),
    ("future_dated", "Future-dated rows", "low"),
]


def audit(parsed: Dict) -> Dict:
    transactions = parsed["transactions"]
    reconciliation = parsed.get("reconciliation", {"breaks": []})

    findings: List[Dict] = []
    findings += check_balance(reconciliation["breaks"])
    findings += check_duplicates(transactions)
    findings += check_periods(parsed.get("periods", []))
    findings += check_totals(parsed, transactions)
    findings += check_unparsed(parsed.get("unparsed", []), transactions)
    findings += check_hygiene(transactions)

    unique = {(f["check"], f["where"], f["detail"]): f for f in findings}
    findings = sorted(unique.values(), key=lambda f: (-f["weight"], f["where"]))

    counts = Counter(f["check"] for f in findings)
    severity = Counter(f["severity"] for f in findings)
    score, verdict, colour = _score(severity, findings, transactions)

    totals = parsed.get("totals", {})
    by_category = defaultdict(lambda: {"in": 0.0, "out": 0.0, "n": 0})
    for txn in transactions:
        cat = category_of(txn["description"])
        bucket = by_category[cat]
        bucket["n"] += 1
        if txn["amount"] > 0:
            bucket["in"] += txn["amount"]
        else:
            bucket["out"] += txn["amount"]

    by_month = defaultdict(lambda: {"in": 0.0, "out": 0.0, "n": 0})
    for txn in transactions:
        if not txn["date"]:
            continue
        key = txn["date"].strftime("%Y-%m")
        by_month[key]["n"] += 1
        if txn["amount"] > 0:
            by_month[key]["in"] += txn["amount"]
        else:
            by_month[key]["out"] += txn["amount"]

    return {
        "findings": findings,
        "counts": counts,
        "severity": severity,
        "score": score,
        "verdict": verdict,
        "verdict_color": colour,
        "transactions": transactions,
        "totals": totals,
        "by_category": {k: {"in": round(v["in"], 2), "out": round(v["out"], 2), "n": v["n"]}
                        for k, v in sorted(by_category.items())},
        "by_month": {k: {"in": round(v["in"], 2), "out": round(v["out"], 2), "n": v["n"]}
                     for k, v in sorted(by_month.items())},
        "periods": parsed.get("periods", []),
        "files": parsed.get("files", []),
        "breaks": reconciliation["breaks"],
        "unparsed": parsed.get("unparsed", []),
    }


def _score(severity, findings, transactions):
    penalty = sum(f["weight"] for f in findings)
    value = max(12.0, min(100.0, 100 - penalty))
    highs = severity.get("high", 0)
    if highs >= 2:
        value = min(value, 55.0)
    elif highs == 1:
        value = min(value, 68.0)   # one break still means "does not reconcile"
    if not transactions:
        return 0.0, "No transactions parsed — check that the PDFs are text-based", "#f87171"
    if value >= 90:
        return round(value, 1), "Reconciled — every balance step checks out", "#34d399"
    if value >= 75:
        return round(value, 1), "Mostly clean — review the flagged rows", "#fbbf24"
    if value >= 55:
        return round(value, 1), "Caveats — the ledger is usable but not proven", "#fb923c"
    return round(value, 1), "Not reconciled — fix the breaks before trusting totals", "#f87171"


def summary_rows(result: Dict) -> List[Dict]:
    rows = []
    for key, label, _ in CHECKS:
        n = result["counts"].get(key, 0)
        if n:
            severities = [f["severity"] for f in result["findings"] if f["check"] == key]
            worst = "high" if "high" in severities else "medium" if "medium" in severities else "low"
            rows.append({"check": label, "count": n, "severity": worst})
    return rows
