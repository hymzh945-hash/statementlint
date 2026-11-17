"""Statement PDFs -> transactions -> a reconciled ledger."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pdfplumber

DATE = re.compile(r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})$")
AMOUNT = re.compile(r"^\(?-?\$?[\d,]*\d\.\d{2}\)?-?$")
PERIOD = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\s*(?:to|-|–|through)\s*"
                    r"(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})", re.I)
OPENING = re.compile(r"opening\s+balance|balance\s+brought\s+forward|b/f", re.I)
CLOSING = re.compile(r"closing\s+balance|balance\s+carried\s+forward", re.I)


def to_date(text: str) -> Optional[date]:
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def to_amount(text: str) -> Optional[float]:
    body = text.replace("$", "").replace(",", "").strip()
    negative = body.startswith("(") or body.endswith("-") or body.startswith("-")
    body = body.strip("()").rstrip("-").lstrip("-")
    try:
        value = float(body)
    except ValueError:
        return None
    return -value if negative else value


def lines_from_pdf(path: str | Path) -> List[List[dict]]:
    """Each page -> list of lines, each line a list of word dicts sorted left to right."""
    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            grouped: Dict[int, List[dict]] = {}
            for word in words:
                grouped.setdefault(round(word["top"]), []).append(word)
            pages.append([sorted(grouped[key], key=lambda w: w["x0"]) for key in sorted(grouped)])
    return pages


def parse_lines(pages: List[List[List[dict]]]) -> Dict:
    transactions: List[dict] = []
    opening = closing = None
    period = None
    unparsed: List[str] = []
    header_count = 0

    for lines in pages:
        for words in lines:
            tokens = [w["text"] for w in words]
            if not tokens:
                continue
            joined = " ".join(tokens)

            if period is None:
                match = PERIOD.search(joined)
                if match:
                    start, end = to_date(match.group(1)), to_date(match.group(2))
                    if start and end:
                        period = (start, end)

            handled_meta = False
            if OPENING.search(joined):
                amounts = [to_amount(t) for t in tokens if AMOUNT.match(t)]
                amounts = [a for a in amounts if a is not None]
                if amounts:
                    opening = amounts[-1]
                    handled_meta = True
            if CLOSING.search(joined):
                amounts = [to_amount(t) for t in tokens if AMOUNT.match(t)]
                amounts = [a for a in amounts if a is not None]
                if amounts:
                    closing = amounts[-1]
                    handled_meta = True
            if handled_meta:
                continue

            amount_tokens = [(w, to_amount(w["text"])) for w in words if AMOUNT.match(w["text"])]
            amount_tokens = [(w, a) for w, a in amount_tokens if a is not None]

            if DATE.match(tokens[0]):
                if not amount_tokens:
                    unparsed.append(joined)
                    continue
                day = to_date(tokens[0])
                amount_word, amount = amount_tokens[0]
                balance_word = amount_tokens[1][0] if len(amount_tokens) > 1 else None
                balance = amount_tokens[1][1] if len(amount_tokens) > 1 else None

                desc_words = [w for w in words[1:]
                              if w["x0"] < amount_word["x0"] - 2
                              and not AMOUNT.match(w["text"])]
                description = " ".join(w["text"] for w in desc_words).strip()
                transactions.append({
                    "date": day,
                    "description": description,
                    "amount": amount,
                    "balance": balance,
                    "balance_x": balance_word["x0"] if balance_word else None,
                    "source": None,  # filled in by load()
                })
                continue

            if "DATE" in joined.upper() and ("AMOUNT" in joined.upper() or "BALANCE" in joined.upper()):
                header_count += 1
                continue

            # continuation of a description (no date, no amount, indented past the date column)
            if (transactions and words and words[0]["x0"] > 60
                    and not amount_tokens and len(tokens) > 1):
                transactions[-1]["description"] += " " + joined
                continue

            if amount_tokens or DATE.search(joined):
                unparsed.append(joined)

    return {"transactions": transactions, "opening": opening, "closing": closing,
            "period": period, "unparsed": unparsed, "headers": header_count}


def load(path: str | Path) -> Dict:
    """One statement file."""
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("statement files must be PDF")
    parsed = parse_lines(lines_from_pdf(path))
    for txn in parsed["transactions"]:
        txn["source"] = path.name
    infer_signs(parsed["transactions"])
    reconciliation = reconcile(parsed["transactions"])
    file_totals = totals(parsed["transactions"])
    parsed["reconciliation"] = reconciliation
    parsed["totals"] = file_totals
    parsed["files"] = [path.name]
    parsed["files_data"] = [{"name": path.name, "opening": parsed["opening"],
                             "closing": parsed["closing"], "totals": file_totals,
                             "breaks": len(reconciliation["breaks"])}]
    return parsed


def load_many(paths: Iterable[str | Path]) -> Dict:
    """Each statement reconciles against its own balance series; the merge is only for
    cross-file checks (duplicates, gaps, totals)."""
    files = [Path(p) for p in paths]
    merged: List[dict] = []
    breaks: List[dict] = []
    per_file: List[dict] = []
    periods = []
    unparsed = []

    for path in files:
        one = load(path)
        infer_signs(one["transactions"])
        reconciliation = reconcile(one["transactions"])
        file_totals = totals(one["transactions"])
        per_file.append({"name": path.name, "opening": one["opening"],
                         "closing": one["closing"], "totals": file_totals,
                         "breaks": len(reconciliation["breaks"])})
        breaks.extend(reconciliation["breaks"])
        merged.extend(one["transactions"])
        unparsed.extend(one["unparsed"])
        if one["period"]:
            periods.append(one["period"])

    merged.sort(key=lambda t: (t["date"] or date.min, t["description"], t["source"] or ""))
    return {"transactions": merged, "periods": periods, "unparsed": unparsed,
            "files": [p.name for p in files], "files_data": per_file,
            "reconciliation": {"breaks": breaks}, "totals": totals(merged),
            "opening": per_file[0]["opening"] if per_file else None,
            "closing": per_file[-1]["closing"] if per_file else None}


def infer_signs(transactions: List[dict]) -> List[dict]:
    """Some banks print unsigned amounts; the balance chain is the ground truth."""
    fixed = 0
    for i in range(1, len(transactions)):
        prev, cur = transactions[i - 1], transactions[i]
        if prev.get("balance") is None or cur.get("balance") is None or cur["amount"] is None:
            continue
        delta = round(cur["balance"] - prev["balance"], 2)
        if abs(delta) < 1e-6:
            continue
        if abs(delta + cur["amount"]) < 0.005 and cur["amount"] > 0:
            cur["amount"] = -cur["amount"]
            cur["sign_inferred"] = True
            fixed += 1
        elif abs(delta - cur["amount"]) > 0.005 and abs(delta + cur["amount"]) < 0.005:
            cur["amount"] = -abs(cur["amount"])
            cur["sign_inferred"] = True
            fixed += 1
    return transactions


def reconcile(transactions: List[dict]) -> Dict:
    """Walk the running balance. Each step is a check the bank itself already did."""
    breaks = []
    for i in range(1, len(transactions)):
        prev, cur = transactions[i - 1], transactions[i]
        if None in (prev.get("balance"), cur.get("balance"), cur.get("amount")):
            continue
        expected = round(prev["balance"] + cur["amount"], 2)
        actual = round(cur["balance"], 2)
        if abs(expected - actual) > 0.005:
            breaks.append({"date": str(cur["date"]), "description": cur["description"],
                           "expected": expected, "actual": actual,
                           "delta": round(actual - expected, 2), "source": cur["source"]})
    return {"breaks": breaks}


def totals(transactions: List[dict]) -> Dict:
    money_in = round(sum(t["amount"] for t in transactions if t["amount"] > 0), 2)
    money_out = round(sum(t["amount"] for t in transactions if t["amount"] < 0), 2)
    return {"count": len(transactions), "in": money_in, "out": money_out,
            "net": round(money_in + money_out, 2)}
