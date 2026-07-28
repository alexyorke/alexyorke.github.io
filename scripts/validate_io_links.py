#!/usr/bin/env python3
"""Validate io_links.md record shape, dates, encoding, and section ordering."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path


DATE_RE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")
path = Path("io_links.md")
raw = path.read_bytes()
assert not raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM is not allowed"
assert b"\r" not in raw, "CR bytes are not allowed"

lines = raw.decode("utf-8").splitlines()
record_count = 0
indexed_count = 0
na_count = 0
future_dates: list[tuple[int, str]] = []
bad_records: list[tuple[int, str]] = []
sort_errors: list[tuple[int, str, str]] = []
previous_date: str | None = None

for line_number, line in enumerate(lines, 1):
    if line.startswith("## "):
        previous_date = None
        continue
    fields = line.split("\t")
    if len(fields) != 3:
        continue
    record_count += 1
    _, status, value = fields
    if status == "indexed":
        indexed_count += 1
    if value == "N/A":
        na_count += 1
    if not DATE_RE.fullmatch(value):
        bad_records.append((line_number, line))
        continue
    normalized = value + "-01" * (3 - len(value.split("-")))
    if date.fromisoformat(normalized) > date.today():
        future_dates.append((line_number, value))
    if previous_date is not None and value < previous_date:
        sort_errors.append((line_number, previous_date, value))
    previous_date = value

assert not bad_records, f"bad date records: {bad_records[:5]}"
assert not future_dates, f"future dates: {future_dates[:5]}"
assert not sort_errors, f"sorting errors: {sort_errors[:5]}"
assert na_count == 0, f"N/A values: {na_count}"

print(
    {
        "lines": len(lines),
        "records": record_count,
        "indexed": indexed_count,
        "N/A": na_count,
        "sort_errors": len(sort_errors),
        "future_dates": len(future_dates),
        "LF_without_BOM": True,
    }
)
