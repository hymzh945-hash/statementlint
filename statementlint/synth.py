"""Build small, valid PDF statements without a PDF library — used by `demo` and tests."""

from __future__ import annotations

from pathlib import Path


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content(lines: list[str], start_y: float = 750, leading: float = 13,
             size: float = 10, x: float = 40) -> bytes:
    parts = [f"BT /F1 {size} Tf {x} {start_y} Td"]
    for i, line in enumerate(lines):
        if i:
            parts.append(f"0 -{leading} Td")
        parts.append(f"({_escape(line)}) Tj")
    parts.append("ET")
    return ("\n".join(parts)).encode("latin-1", "replace")


def write_pdf(path: str | Path, lines: list[str]) -> Path:
    path = Path(path)
    content = _content(lines)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n"
            f"{xref_at}\n%%EOF\n").encode()
    path.write_bytes(bytes(out))
    return path


def statement(period: str, opening: float, rows: list[tuple], closing: float,
              bank: str = "ACME BANK", account: str = "**** 4821") -> list[str]:
    """rows: (date, description, amount, balance)"""
    lines = [
        bank,
        f"Account {account} - Statement period {period}",
        "",
        f"Opening balance  {opening:,.2f}",
        "",
        "DATE        DESCRIPTION                              AMOUNT      BALANCE",
        "-" * 72,
    ]
    for date, desc, amount, balance in rows:
        lines.append(f"{date:<11} {desc:<40} {amount:>10,.2f} {balance:>11,.2f}")
    lines += ["-" * 72, f"Closing balance  {closing:,.2f}", "",
              "Questions? Call 1-800-000-0000."]
    return lines
