#!/usr/bin/env python3
"""Resolve cljdoc pages from Clojars version publication timestamps."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


DOC_RE = re.compile(r"/d/([^/]+)/([^/]+)/([^/]+)(?:/.*)?$")
PUSHED_RE = re.compile(r'<span title="(\d{4}-\d{2}-\d{2}) [^"]+">')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/cljdoc-date-audit.json")
    )
    args = parser.parse_args()

    targets = {}
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if parsed.netloc.lower() != "cljdoc.org":
            continue
        match = DOC_RE.fullmatch(unquote(parsed.path))
        if match:
            targets[parts[0]] = match.groups()

    session = requests.Session()
    results = []
    for url, (group, artifact, requested_version) in targets.items():
        version = requested_version
        api_url = f"https://clojars.org/api/artifacts/{group}/{artifact}"
        if version == "CURRENT":
            api_response = session.get(api_url, timeout=30)
            if api_response.ok:
                version = api_response.json().get("latest_release")
        version_url = f"https://clojars.org/{artifact}/versions/{version}"
        response = session.get(version_url, timeout=30)
        match = PUSHED_RE.search(response.text) if response.ok else None
        date = match.group(1) if match else None
        results.append(
            {
                "url": url,
                "status": "uploaded" if date else None,
                "date": date,
                "source": version_url,
                "evidence": {
                    "group": group,
                    "artifact": artifact,
                    "resolved_version": version,
                    "http_status": response.status_code,
                },
            }
        )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(results, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Resolved {sum(bool(item['date']) for item in results)}/{len(results)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
