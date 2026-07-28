#!/usr/bin/env python3
"""Revert embedded-date results invalidated by stricter source checks."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse


INPUT = Path("io_links.md")
REPORT = Path("scratch/embedded-web-dates-audit.json")
INDEX_DATE = "2026-07-27"


def main() -> None:
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    invalid = {}
    for item in payload["results"]:
        value = item.get("date")
        if not value:
            continue
        is_dblp = urlparse(item["url"]).hostname == "dblp.org"
        near_audit = (
            item.get("evidence", "").startswith("HTTP Last-Modified:")
            and date.fromisoformat(value) >= date.fromisoformat(INDEX_DATE) - timedelta(days=1)
        )
        http_error = (
            item.get("evidence", "").startswith("HTTP Last-Modified:")
            and item.get("http_status", 200) >= 400
        )
        if is_dblp or near_audit or http_error:
            invalid[item["url"]] = (item["status"], value)

    lines = INPUT.read_text(encoding="utf-8").splitlines()
    changed = 0
    for index, line in enumerate(lines):
        fields = line.split("\t")
        expected = invalid.get(fields[0]) if len(fields) == 3 else None
        if expected and tuple(fields[1:]) == expected:
            lines[index] = f"{fields[0]}\tindexed\t{INDEX_DATE}"
            changed += 1
    INPUT.write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"reverted={changed} invalid_candidates={len(invalid)}")


if __name__ == "__main__":
    main()
