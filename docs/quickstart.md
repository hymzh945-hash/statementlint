# StatementLint Pro — quickstart

## 1. Install

```bash
pip install statementlint
```

Python 3.9+, one dependency (`pdfplumber`).

## 2. Store your licence

```bash
mkdir -p ~/.statementlint
mv ~/Downloads/statementlint-license.json ~/.statementlint/license.json
statementlint license
```

`Pro license · you@example.com · expires 2027-11-18`

## 3. Parse your statements

```bash
statementlint parse -i jan.pdf feb.pdf mar.pdf --csv ledger.csv --report audit.html
```

Order doesn't matter; files are matched by their statement period, not their name.

## 4. Read the result

- **Score 34/100** with `Not reconciled` means the balance chain broke somewhere. Fix that
  first — totals mean nothing until the chain holds.
- **Balance chain breaks** lists the exact row: expected figure, statement figure, difference.
  A 0.10 break is usually a rounding row; a break of exactly one transaction's amount is
  almost always a dropped row.
- **Duplicate transactions** across two overlapping statements is normal when you re-download
  a month. The CSV keeps both; sum only the first.
- **Rows that failed to parse** is your extraction coverage. Under 5% is cosmetic; over 20%
  means the layout isn't supported yet — send me the file.

## 5. Make sure it's not guessing

```bash
statementlint demo -o /tmp/demo
```

Builds two statements with a planted 0.10 break, an overlap duplicate, an 8-day gap and a
totals mismatch, then reconciles them. Open `/tmp/demo/statementlint-report.html`.

## Common questions

**Scanned statements?**
Run `ocrmypdf --force-ocr scan.pdf text.pdf` first. StatementLint reads text, not pixels.

**Day-first dates (03/04 = 3 April)?**
They're read month-first. It will show up instantly as chain breaks, because the amounts land
in the wrong order. There's no silent wrong answer here.

**Does it upload my statements?**
No. No network calls at all.

**Can I categorise differently?**
The CSV has a `category` column from built-in merchant rules. Edit that column in your
spreadsheet and keep your own mapping.
