#!/usr/bin/env python3
"""Resolve nLab page creation dates from each page's first revision."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests


REVISION_DATE_RE = re.compile(
    r'<div\s+class="revisedby">.*?Revision on\s+'
    r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})\s+at\s+(\d{2}:\d{2}:\d{2})",
    re.I | re.S,
)
USER_AGENT = "io-links-date-audit/1.0"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/ncatlab-continuation-audit.json")
    )
    args = parser.parse_args()

    targets = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        parsed = urlparse(fields[0])
        if parsed.hostname != "ncatlab.org" or "/nlab/show/" not in parsed.path:
            continue
        name = unquote(parsed.path.split("/nlab/show/", 1)[1])
        targets.append((fields[0], name))

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    results = []
    for index, (url, name) in enumerate(targets, 1):
        revision_url = (
            "https://ncatlab.org/nlab/revision/" + quote(name, safe="-_()") + "/1"
        )
        try:
            response = session.get(revision_url, timeout=30)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            match = REVISION_DATE_RE.search(response.text)
            if not match:
                raise RuntimeError("first-revision timestamp not found")
            timestamp = datetime.strptime(
                " ".join(match.groups()), "%B %d, %Y %H:%M:%S"
            )
            results.append(
                {
                    "url": url,
                    "status": "created",
                    "date": timestamp.date().isoformat(),
                    "evidence": f"nLab revision 1 timestamp: {timestamp.isoformat()}",
                    "source": revision_url,
                }
            )
        except Exception as error:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": f"{type(error).__name__}: {error}",
                    "source": revision_url,
                }
            )
        time.sleep(0.2)

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
