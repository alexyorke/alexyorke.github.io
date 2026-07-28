#!/usr/bin/env python3
"""Transfer dates across trivial URL aliases already present in io_links.md."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit


INPUT = Path("io_links.md")
REPORT = Path("scratch/canonical-duplicate-dates-audit.json")
TRACKING = {
    "ref",
    "source",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def canonical(url: str) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    port = f":{parsed.port}" if parsed.port and parsed.port not in {80, 443} else ""
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in TRACKING
        ]
    )
    return host + port, path, query


def main() -> None:
    rows = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) == 3:
            rows.append(fields)
    groups: dict[tuple[str, str, str], list[list[str]]] = defaultdict(list)
    for row in rows:
        groups[canonical(row[0])].append(row)

    results = []
    for url, status, _ in rows:
        if status != "indexed":
            continue
        resolved = [row for row in groups[canonical(url)] if row[1] != "indexed"]
        values = {(row[1], row[2]) for row in resolved}
        if len(values) != 1:
            continue
        new_status, value = values.pop()
        source_url = resolved[0][0]
        results.append(
            {
                "url": url,
                "status": new_status,
                "date": value,
                "evidence": "Same resource as an already dated URL differing only by scheme, www, trailing slash, or tracking query.",
                "source": source_url,
            }
        )

    payload = {
        "target_count": len(results),
        "resolved_count": len(results),
        "unresolved_count": 0,
        "results": results,
    }
    REPORT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in payload.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()
