#!/usr/bin/env python3
"""Resolve Google Groups conversation dates from the visible first message."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


DATE_RE = re.compile(
    r"^[A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4},\s+"
    r"\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M$",
    re.I,
)
USER_AGENT = "Mozilla/5.0 (compatible; io-links-date-audit/1.0)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("scratch/google-groups-continuation-audit.json"),
    )
    args = parser.parse_args()

    targets = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        parsed = urlparse(fields[0])
        if parsed.hostname != "groups.google.com":
            continue
        parts = parsed.path.strip("/").split("/")
        if "c" not in parts:
            continue
        message_id = None
        if "m" in parts:
            message_index = parts.index("m")
            if message_index + 1 < len(parts):
                message_id = parts[message_index + 1]
        targets.append((fields[0], message_id))

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    results = []
    for url, message_id in targets:
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            scope = soup
            if message_id:
                scope = soup.select_one(f'section[data-doc-id="{message_id}"]')
                if scope is None:
                    raise RuntimeError("linked reply not found in conversation HTML")
            candidates = [
                node.get_text(" ", strip=True).replace("\u202f", " ")
                for node in scope.select("span.zX2W9c")
            ]
            raw = next((value for value in candidates if DATE_RE.fullmatch(value)), None)
            if not raw:
                raise RuntimeError("visible first-message timestamp not found")
            timestamp = date_parser.parse(raw, fuzzy=False, default=datetime(1, 1, 1))
            results.append(
                {
                    "url": url,
                    "status": "published",
                    "date": timestamp.date().isoformat(),
                    "evidence": (
                        f"Google Groups visible linked-reply timestamp: {raw}"
                        if message_id
                        else f"Google Groups visible first-message timestamp: {raw}"
                    ),
                    "source": url,
                }
            )
        except Exception as error:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": f"{type(error).__name__}: {error}",
                    "source": url,
                }
            )
        time.sleep(0.25)

    report = {
        "target_count": len(results),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in report.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()
