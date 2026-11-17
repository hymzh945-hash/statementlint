# StatementLint

**Bank statements that reconcile, or a list of exactly why they don't.**

Drag in the PDFs. StatementLint parses every row, rebuilds the running balance, and tells you
where the chain breaks — the one thing a spreadsheet import never checks.

```
statementlint parse -i statement-2026-01.pdf statement-2026-02.pdf --csv ledger.csv --report audit.html
```

```
StatementLint 0.1.0 · 2 file(s)
  score      34/100  Not reconciled — fix the breaks before trusting totals
  rows       12 transactions (1 balance break)
  in / out   4,800.00 / -2,460.88  net 2,339.12
  - Balance chain breaks                1  [high]
  - Duplicate transactions              1  [high]
  - Gaps between statements             1  [medium]
  - Opening + movements ≠ closing       2  [medium]
```

## Why the balance chain matters

Every bank statement prints a running balance next to each row. That column is a checksum:
`previous balance + amount = this balance`, for every single row, already verified by the bank.

If one step doesn't match, something is missing — a page that didn't export, a row the OCR
dropped, a duplicate import, or a transaction your parser mis-signed. StatementLint walks
that chain and reports the exact step, the expected figure, and the difference.

## What it checks

| Check | Severity | Meaning |
|---|---|---|
| Balance chain breaks | high | A row's balance doesn't follow from the previous row + amount |
| Duplicate transactions | high | Same date, amount and description twice — usually a double import |
| Gaps between statements | medium/high | Missing days between one statement's end and the next's start |
| Opening + movements ≠ closing | medium | The statement's own totals don't add up with what was parsed |
| No running balance | medium | Chain cannot be verified at all (some exports omit it) |
| Rows that failed to parse | medium | Extraction coverage, stated honestly with a sample |
| Signs inferred | low | Unsigned amounts recovered from the balance movement |
| Zero amounts / future dates | low | Hygiene |

## Output

- **`ledger.csv`** — date, description, amount, balance, source file, category. Sortable,
  importable, one row per transaction.
- **`audit.html`** — score, verdict, totals, by-month and by-category tables, and (Pro) the
  break list with expected vs actual.

## Free vs Pro

| | Free | Pro |
|---|---|---|
| Parse PDFs to a ledger + CSV | yes | yes |
| Score and check counts | yes | yes |
| The break list (expected / actual / delta) | — | yes |
| Full findings table in the report | — | yes |

Pro is a signed licence file verified locally — no server, no telemetry, no network calls at
all. `docs/quickstart.md` covers install and licence placement.

## Scope, honestly

- **Text-based PDFs only.** A scanned statement is an image; run OCR first
  (`ocrmypdf --force-ocr in.pdf out.pdf`), then point StatementLint at the result.
- **One table layout per statement.** Date on the left, amount and balance on the right.
  Statements that put amounts in separate debit/credit columns with no running balance are
  parsed as rows but cannot be chain-verified, and say so.
- **Dates are read, not guessed.** Ambiguous `03/04/2026` is read month-first. If your bank
  is day-first, the reconciliation will expose it immediately as a chain break.
- **It does not categorise perfectly.** Built-in rules cover the common merchant strings;
  "Other" is honest about what it doesn't know.

## Install

```
pip install statementlint
pip install -e ".[dev]"
```

Python 3.9+. One runtime dependency: `pdfplumber`.

## Commands

```
statementlint parse -i a.pdf b.pdf --csv ledger.csv --report audit.html
statementlint demo -o /tmp/demo        # builds two statements with planted problems
statementlint license
```

## Pro edition

The paid edition adds the HTML report templates, CSV exports, and an offline-verified signed
licence — no server check, no telemetry. $29 once, yours to keep:

https://hymz.gumroad.com/l/statementlint

## Built on

`pdfplumber` (MIT) for PDF text extraction. StatementLint adds the layout parser, the
reconciliation engine, the checks, scoring, report and licence layer. See `NOTICE`.

## Licence

Business source: free for your own statements, including commercial use. Redistribution or
resale of the source requires a commercial licence — see `LICENSE`.
