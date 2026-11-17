"""StatementLint HTML report."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Dict, List

from .checks import summary_rows

CSS = """
:root{--bg:#0b0f18;--panel:#121a29;--line:#22304a;--fg:#e8eef8;--muted:#8b9ab1;
--accent:#38bdf8;--good:#34d399;--warn:#fbbf24;--bad:#f87171}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1060px;margin:0 auto;padding:34px 24px 60px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:32px 0 10px}
.sub{color:var(--muted);font-size:13px}
.hero{display:flex;gap:20px;align-items:center;background:var(--panel);border:1px solid var(--line);
border-radius:14px;padding:20px 22px;margin-top:18px}
.hero .score{font-size:40px;font-weight:700;letter-spacing:-.03em;line-height:1}
.hero .vt{font-size:15.5px;font-weight:650}
.hero .vd{color:var(--muted);font-size:12.5px;margin-top:4px}
.meta{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:12px;color:var(--muted);margin-top:12px}
.meta b{color:var(--fg)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:13px 15px}
.card .l{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
.card .v{font-size:22px;font-weight:650;margin-top:5px}
.card .f{font-size:10.5px;color:var(--muted);margin-top:2px}
table{width:100%;border-collapse:collapse;margin-top:6px;font-size:12.5px}
th{text-align:left;color:var(--muted);font-weight:600;font-size:10.5px;text-transform:uppercase;
letter-spacing:.06em;border-bottom:1px solid var(--line);padding:7px 9px}
td{padding:7px 9px;border-bottom:1px solid #1a2436;vertical-align:top}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:10.5px;
text-transform:uppercase;letter-spacing:.06em}
.badge.high{background:rgba(248,113,113,.14);color:#f87171}
.badge.medium{background:rgba(251,191,36,.14);color:#fbbf24}
.badge.low{background:rgba(139,154,177,.14);color:#8b9ab1}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:#cfe3f7}
.lock{background:linear-gradient(135deg,#131c2c,#0d1420);border:1px dashed var(--line);
border-radius:13px;padding:20px;text-align:center;margin-top:10px}
.lock .t{font-weight:650} .lock .d{color:var(--muted);font-size:12.5px;margin:6px auto 12px;max-width:520px}
.lock a{display:inline-block;background:var(--accent);color:#05121c;text-decoration:none;
font-weight:650;padding:9px 17px;border-radius:9px;font-size:13px}
footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);
font-size:11.5px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
"""


def money(value: float) -> str:
    return f"{value:,.2f}" if value >= 0 else f"({abs(value):,.2f})"


def _table(headers: List[str], rows: List[List[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(
        f'<td class="{"num" if i else ""}">{cell}</td>' for i, cell in enumerate(row)
    ) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build(result: Dict, pro: bool = False, version: str = "0.1.0", top: int = 30) -> str:
    t = result["totals"]
    files = result.get("files") or []
    periods = result.get("periods") or []
    period_text = f"{min(p[0] for p in periods)} → {max(p[1] for p in periods)}" if periods else "unknown"

    cards = [
        ("Score", f"{result['score']:.0f}", "/ 100"),
        ("Transactions", f"{t.get('count', 0):,}", f"{len(files)} statement(s)"),
        ("Money in", money(t.get("in", 0)), "credits"),
        ("Money out", money(t.get("out", 0)), "debits"),
        ("Net", money(t.get("net", 0)), "movements"),
        ("Breaks", str(len(result["breaks"])), "balance mismatches"),
    ]
    card_html = "".join(
        f'<div class="card"><div class="l">{l}</div><div class="v">{v}</div>'
        f'<div class="f">{f}</div></div>' for l, v, f in cards)

    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StatementLint — {html.escape(', '.join(files)) or 'statements'}</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>StatementLint — reconciled ledger</h1>
<div class="sub">Parsed from the PDFs, then checked step by step against the running balance.</div>
<div class="hero"><div><div class="score" style="color:{result['verdict_color']}">{result['score']:.0f}</div>
<div class="sub">/ 100</div></div>
<div><div class="vt" style="color:{result['verdict_color']}">{html.escape(result['verdict'])}</div>
<div class="vd">{len(result['findings'])} findings · {result['severity'].get('high', 0)} high ·
{result['severity'].get('medium', 0)} medium · {result['severity'].get('low', 0)} low</div></div></div>
<div class="meta"><span>files <b>{html.escape(', '.join(files)) or '—'}</b></span>
<span>period <b>{period_text}</b></span>
<span>generated <b>{datetime.now():%Y-%m-%d %H:%M}</b></span></div>
<div class="cards">{card_html}</div>
"""]

    rows = summary_rows(result)
    if rows:
        parts.append("<h2>What was found</h2>" + _table(
            ["Check", "Count", "Severity"],
            [[html.escape(r["check"]), str(r["count"]),
              f'<span class="badge {r["severity"]}">{r["severity"]}</span>'] for r in rows]))

    if result["breaks"] and pro:
        parts.append("<h2>Where the chain breaks</h2>" + _table(
            ["Date", "Description", "Expected balance", "Statement says", "Off by"],
            [[html.escape(b["date"]), html.escape(b["description"][:44]),
              money(b["expected"]), money(b["actual"]), f"{b['delta']:+,.2f}"]
             for b in result["breaks"][:top]]))

    parts.append("<h2>By month</h2>" + _table(
        ["Month", "Rows", "In", "Out", "Net"],
        [[k, str(v["n"]), money(v["in"]), money(v["out"]), money(round(v["in"] + v["out"], 2))]
         for k, v in result["by_month"].items()]))

    parts.append("<h2>By category</h2>" + _table(
        ["Category", "Rows", "In", "Out"],
        [[k, str(v["n"]), money(v["in"]), money(v["out"])]
         for k, v in result["by_category"].items()]))

    if pro:
        parts.append("<h2>Findings</h2>" + _table(
            ["Severity", "Check", "Where", "Detail"],
            [[f'<span class="badge {f["severity"]}">{f["severity"]}</span>',
              html.escape(f["check"]), f'<span class="mono">{html.escape(f["where"])}</span>',
              html.escape(f["detail"])] for f in result["findings"][:top]]))
    else:
        parts.append("""<h2>Findings</h2><div class="lock"><div class="t">The break list is Pro</div>
<div class="d">Pro shows every balance mismatch with the expected figure, the statement's figure
and the difference, plus the full findings table and CSV export.</div>
<a href="https://statementlint.gumroad.com">Get StatementLint Pro</a></div>""")

    parts.append(f"""<footer><span>StatementLint {version} · built on pdfplumber (MIT)</span>
<span>Text-based PDFs only; scanned statements need OCR first.</span></footer></div></body></html>""")
    return "".join(parts)
