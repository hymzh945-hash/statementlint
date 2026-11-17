"""StatementLint tests — PDF in, reconciled ledger out."""

from __future__ import annotations

import base64
import json
from datetime import date

import pytest

from statementlint import checks, licensing, parse, report, synth

JAN = [
    ("01/03/2026", "WHOLE FOODS MKT 4821", -84.12, 4115.88),
    ("01/04/2026", "PAYROLL DEPOSIT ACME INC", 2400.00, 6515.88),
    ("01/07/2026", "STARBUCKS STORE 0441", -6.75, 6509.13),
]


def pdf(tmp_path, rows, opening=4200.00, closing=6509.13, period="01/01/2026 to 01/31/2026",
        name="s.pdf"):
    path = tmp_path / name
    synth.write_pdf(path, synth.statement(period, opening, rows, closing))
    return path


def test_parse_reads_dates_descriptions_amounts(tmp_path):
    parsed = parse.load(pdf(tmp_path, JAN))
    assert len(parsed["transactions"]) == 3
    first = parsed["transactions"][0]
    assert first["date"] == date(2026, 1, 3)
    assert "WHOLE FOODS" in first["description"]
    assert first["amount"] == -84.12
    assert first["balance"] == 4115.88
    assert parsed["unparsed"] == []


def test_metadata_lines_captured_and_not_counted_as_transactions(tmp_path):
    parsed = parse.load(pdf(tmp_path, JAN))
    assert parsed["opening"] == 4200.0
    assert parsed["closing"] == 6509.13
    assert parsed["period"] == (date(2026, 1, 1), date(2026, 1, 31))


def test_clean_chain_has_no_breaks(tmp_path):
    parsed = parse.load(pdf(tmp_path, JAN))
    parse.infer_signs(parsed["transactions"])
    assert parse.reconcile(parsed["transactions"])["breaks"] == []


def test_broken_balance_is_reported_with_the_delta(tmp_path):
    rows = list(JAN)
    rows[2] = ("01/07/2026", "STARBUCKS STORE 0441", -6.75, 6509.23)   # +0.10 off
    parsed = parse.load(pdf(tmp_path, rows))
    breaks = parse.reconcile(parsed["transactions"])["breaks"]
    assert len(breaks) == 1
    assert breaks[0]["delta"] == pytest.approx(0.10, abs=1e-6)


def test_duplicate_across_two_statements(tmp_path):
    jan = pdf(tmp_path, JAN, name="jan.pdf")
    feb = pdf(tmp_path, [JAN[2], ("02/10/2026", "NETFLIX", -15.49, 6493.64)],
              opening=6509.13, closing=6493.64, period="02/01/2026 to 02/28/2026", name="feb.pdf")
    parsed = parse.load_many([jan, feb])
    result = checks.audit(parsed)
    duplicates = [f for f in result["findings"] if f["check"] == "duplicate_transaction"]
    assert len(duplicates) == 1
    assert "2 identical rows" in duplicates[0]["detail"]


def test_period_gap_is_flagged(tmp_path):
    jan = pdf(tmp_path, JAN, name="jan.pdf")
    feb = pdf(tmp_path, [("02/20/2026", "SHOP", -10.00, 6499.13)],
              opening=6509.13, closing=6499.13, period="02/20/2026 to 02/28/2026", name="feb.pdf")
    result = checks.audit(parse.load_many([jan, feb]))
    assert any(f["check"] == "period_gap" for f in result["findings"])


def test_totals_mismatch_detected(tmp_path):
    parsed = parse.load(pdf(tmp_path, JAN, closing=6500.00))
    result = checks.audit(parsed)
    assert any(f["check"] == "totals_mismatch" for f in result["findings"])


def test_zero_amount_row_is_low_severity(tmp_path):
    rows = JAN + [("01/09/2026", "ADJUSTMENT", 0.00, 6509.13)]
    result = checks.audit(parse.load(pdf(tmp_path, rows)))
    zero = [f for f in result["findings"] if f["check"] == "zero_amount"]
    assert zero and zero[0]["severity"] == "low"


def test_sign_inference_from_balance_chain():
    txns = [
        {"date": date(2026, 1, 3), "description": "A", "amount": 100.00, "balance": 400.00},
        {"date": date(2026, 1, 4), "description": "B", "amount": 84.12, "balance": 315.88},
    ]
    parse.infer_signs(txns)
    assert txns[1]["amount"] == -84.12
    assert txns[1]["sign_inferred"] is True


def test_categories_are_assigned():
    assert checks.category_of("WHOLE FOODS MKT") == "Groceries"
    assert checks.category_of("PAYROLL DEPOSIT") == "Income"
    assert checks.category_of("NETFLIX SUBSCRIPTION") == "Subscriptions"
    assert checks.category_of("XYZ RANDOM") == "Other"


def test_clean_statement_scores_high(tmp_path):
    result = checks.audit(parse.load(pdf(tmp_path, JAN)))
    assert result["score"] >= 90
    assert "Reconciled" in result["verdict"]


def test_broken_statement_scores_low(tmp_path):
    rows = list(JAN)
    rows[2] = ("01/07/2026", "STARBUCKS", -6.75, 6509.93)
    result = checks.audit(parse.load(pdf(tmp_path, rows, closing=6999.00)))
    assert result["score"] <= 70
    assert result["verdict_color"] in {"#fb923c", "#f87171"}


def test_month_and_category_tables_are_populated(tmp_path):
    result = checks.audit(parse.load(pdf(tmp_path, JAN)))
    assert "2026-01" in result["by_month"]
    assert result["by_month"]["2026-01"]["n"] == 3
    assert "Groceries" in result["by_category"]


def test_report_locks_findings_when_free(tmp_path):
    result = checks.audit(parse.load(pdf(tmp_path, JAN, closing=6500.00)))
    free = report.build(result, pro=False)
    assert "The break list is Pro" in free
    assert "The break list is Pro" not in report.build(result, pro=True)


def test_non_pdf_rejected(tmp_path):
    bad = tmp_path / "x.csv"
    bad.write_text("a,b\n")
    with pytest.raises(ValueError):
        parse.load(bad)


def test_bad_license_falls_back_to_free(tmp_path, monkeypatch):
    doc = {"payload": {"product": "statementlint"}, "sig": base64.b64encode(b"x").decode()}
    path = tmp_path / "lic.json"
    path.write_text(json.dumps(doc))
    monkeypatch.setenv("STATEMENTLINT_LICENSE", str(path))
    assert licensing.status()["valid"] is False


def test_demo_cli_runs_end_to_end(tmp_path, capsys):
    from statementlint import cli
    rc = cli.main(["demo", "-o", str(tmp_path / "demo")])
    assert rc == 0
    assert (tmp_path / "demo" / "statementlint-report.html").exists()
    assert (tmp_path / "demo" / "statement-2026-01.pdf").exists()
