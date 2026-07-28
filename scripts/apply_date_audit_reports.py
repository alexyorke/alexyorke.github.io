#!/usr/bin/env python3
"""Apply resolved date-audit JSON records to currently indexed io_links rows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DATE_RE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")
ALLOWED_STATUSES = {
    "archived",
    "created",
    "modified",
    "publication",
    "published",
    "updated",
    "uploaded",
}


def records(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("results", "resolved"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("report must be an array or contain a results/resolved array")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--input", type=Path, default=Path("io_links.md"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--from-status",
        action="append",
        default=[],
        help="Only replace rows with this current status; defaults to indexed.",
    )
    args = parser.parse_args()
    if not args.from_status:
        args.from_status = ["indexed"]

    updates: dict[str, tuple[str, str, str]] = {}
    for report in args.reports:
        payload = json.loads(report.read_text(encoding="utf-8"))
        for item in records(payload):
            url = item.get("url")
            status = item.get("status")
            value = item.get("date")
            if not (url and status and value):
                continue
            if status not in ALLOWED_STATUSES:
                raise ValueError(f"{report}: unsupported status {status!r} for {url}")
            if not DATE_RE.fullmatch(value):
                raise ValueError(f"{report}: malformed date {value!r} for {url}")
            update = (status, value, str(report))
            previous = updates.get(url)
            if previous and previous[:2] != update[:2]:
                raise ValueError(
                    f"conflicting updates for {url}: {previous[:2]} vs {update[:2]}"
                )
            updates[url] = update

    lines = args.input.read_text(encoding="utf-8").splitlines()
    applied = []
    skipped = []
    for index, line in enumerate(lines):
        fields = line.split("\t")
        if len(fields) != 3 or fields[0] not in updates:
            continue
        status, value, report = updates[fields[0]]
        if fields[1] not in set(args.from_status):
            skipped.append(
                {
                    "url": fields[0],
                    "reason": f"current status is {fields[1]}",
                    "report": report,
                }
            )
            continue
        lines[index] = f"{fields[0]}\t{status}\t{value}"
        applied.append(
            {"url": fields[0], "status": status, "date": value, "report": report}
        )

    missing = sorted(set(updates) - {item["url"] for item in applied + skipped})
    if missing:
        raise ValueError(f"{len(missing)} report URLs not found in input; first: {missing[0]}")
    if args.apply:
        args.input.write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
    print(
        {
            "report_updates": len(updates),
            "applied": len(applied),
            "skipped_nonindexed": len(skipped),
        }
    )


if __name__ == "__main__":
    main()
