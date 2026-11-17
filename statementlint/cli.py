"""`statementlint parse | demo | license`."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import checks, licensing, parse, report, synth
from .version import __version__

URL = "https://statementlint.gumroad.com"


def cmd_parse(args: argparse.Namespace) -> int:
    pro = licensing.is_pro()
    parsed = parse.load_many(args.input)
    result = checks.audit(parsed)

    print(f"\nStatementLint {__version__} · {len(args.input)} file(s)")
    print(f"  score      {result['score']:.0f}/100  {result['verdict']}")
    print(f"  rows       {result['totals'].get('count', 0)} transactions "
          f"({len(result['breaks'])} balance breaks)")
    print(f"  in / out   {result['totals'].get('in', 0):,.2f} / "
          f"{result['totals'].get('out', 0):,.2f}  net {result['totals'].get('net', 0):,.2f}")
    for row in checks.summary_rows(result):
        print(f"  - {row['check']:<38} {row['count']:>3}  [{row['severity']}]")

    if args.csv:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", "description", "amount", "balance", "source",
                             "category"])
            for txn in result["transactions"]:
                writer.writerow([txn["date"], txn["description"],
                                 f"{txn['amount']:.2f}",
                                 "" if txn["balance"] is None else f"{txn['balance']:.2f}",
                                 txn["source"], checks.category_of(txn["description"])])
        print(f"\nledger -> {out}")

    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report.build(result, pro=pro, version=__version__), "utf-8")
        print(f"report -> {out} ({'Pro' if pro else 'free tier'})")
    return 0


def demo_pdfs(out: Path) -> list[Path]:
    jan_rows = [
        ("01/03/2026", "WHOLE FOODS MKT 4821", -84.12, 4115.88),
        ("01/04/2026", "PAYROLL DEPOSIT ACME INC", 2400.00, 6515.88),
        ("01/07/2026", "STARBUCKS STORE 0441", -6.75, 6509.13),
        ("01/12/2026", "AMAZON MKTP US", -39.99, 6469.14),
        ("01/20/2026", "RENT PAYMENT JAN", -1850.00, 4619.14),
        ("01/26/2026", "SHELL OIL 57421", -52.30, 4566.84),
        ("01/31/2026", "ACME SUBSCRIPTION", -12.00, 4554.94),
    ]
    jan = synth.write_pdf(out / "statement-2026-01.pdf",
                          synth.statement("01/01/2026 to 01/31/2026", 4200.00, jan_rows, 4554.74))

    feb_rows = [
        ("01/12/2026", "AMAZON MKTP US", -39.99, 4554.94),   # double-imported row
        ("02/16/2026", "BLUE BOTTLE COFFEE", -5.40, 4549.54),
        ("02/20/2026", "PAYROLL DEPOSIT ACME INC", 2400.00, 6949.54),
        ("02/22/2026", "ADJUSTMENT", 0.00, 6949.54),
        ("02/28/2026", "NETFLIX SUBSCRIPTION", -15.49, 6934.05),
    ]
    feb = synth.write_pdf(out / "statement-2026-02.pdf",
                          synth.statement("02/08/2026 to 02/28/2026", 4554.94, feb_rows, 6934.05))
    return [jan, feb]


def cmd_demo(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = demo_pdfs(out)
    parsed = parse.load_many(files)
    result = checks.audit(parsed)

    print(f"{len(result['transactions'])} rows · score {result['score']:.0f} · {result['verdict']}")
    for row in checks.summary_rows(result):
        print(f"  - {row['check']}: {row['count']}")

    (out / "statementlint-report.html").write_text(
        report.build(result, pro=licensing.is_pro(), version=__version__), "utf-8")
    print(f"report -> {out / 'statementlint-report.html'}")
    return 0


def cmd_license(args: argparse.Namespace) -> int:
    st = licensing.status()
    if st["valid"]:
        print(f"Pro license · {st['email']} · expires {st['expires'] or 'lifetime'}")
    else:
        print(f"Free tier · {st['info']}\nPro: {URL}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="statementlint",
                                description="Reconcile bank statements into a ledger that adds up.")
    p.add_argument("--version", action="version", version=f"statementlint {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("parse", help="parse one or more statement PDFs")
    s.add_argument("-i", "--input", nargs="+", required=True)
    s.add_argument("--csv", help="write the ledger to CSV")
    s.add_argument("--report", help="write an HTML report")
    s.set_defaults(func=cmd_parse)

    d = sub.add_parser("demo", help="build two demo statements and reconcile them")
    d.add_argument("-o", "--out", default="statementlint-demo")
    d.set_defaults(func=cmd_demo)

    sub.add_parser("license", help="license status").set_defaults(func=cmd_license)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
