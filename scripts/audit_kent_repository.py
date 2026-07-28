#!/usr/bin/env python3
"""Resolve Kent Academic Repository dates through its OAI-PMH records."""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import requests


DC = "{http://purl.org/dc/elements/1.1/}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/kent-repository-audit.json")
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
    session = requests.Session()
    lines = args.file.read_text(encoding="utf-8").splitlines()
    targets: dict[str, str | None] = {}
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if parsed.netloc.lower() != "kar.kent.ac.uk":
            continue
        match = re.search(r"^/(?:id/eprint/)?(\d+)(?:/|$)", parsed.path)
        eprint_id = match.group(1) if match else None
        if parsed.path.startswith("/id/document/"):
            try:
                response = session.get(
                    parts[0],
                    headers={"User-Agent": "io-links-date-audit/1.0"},
                    timeout=30,
                    verify=False,
                    allow_redirects=True,
                    stream=True,
                )
                redirected = re.match(r"^/(\d+)(?:/|$)", urlparse(response.url).path)
                eprint_id = redirected.group(1) if redirected else None
                response.close()
            except requests.RequestException:
                eprint_id = None
        targets[parts[0]] = eprint_id

    records: dict[str, dict] = {}
    for eprint_id in sorted({value for value in targets.values() if value}):
        response = session.get(
            "https://kar.kent.ac.uk/cgi/oai2",
            params={
                "verb": "GetRecord",
                "metadataPrefix": "oai_dc",
                "identifier": f"oai:kar.kent.ac.uk:{eprint_id}",
            },
            headers={"User-Agent": "io-links-date-audit/1.0"},
            timeout=30,
            verify=False,
        )
        item = {
            "eprint_id": eprint_id,
            "status": None,
            "date": None,
            "source": "kent-oai-pmh",
            "http_status": response.status_code,
        }
        if response.ok:
            try:
                root = ET.fromstring(response.content)
            except ET.ParseError:
                root = None
            dates = (
                [
                    (node.text or "").strip()
                    for node in root.iter(f"{DC}date")
                    if (node.text or "").strip()
                ]
                if root is not None
                else []
            )
            if dates:
                item.update(
                    status="publication",
                    date=dates[0],
                    evidence=f"dc:date {dates[0]}",
                )
        records[eprint_id] = item

    results = []
    for url, eprint_id in targets.items():
        base = records.get(eprint_id or "", {})
        results.append({"url": url, **base})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if args.apply:
        resolved = {item["url"]: item for item in results if item.get("date")}
        changed = 0
        for index, line in enumerate(lines):
            parts = line.split("\t")
            item = resolved.get(parts[0]) if len(parts) == 3 else None
            if len(parts) == 3 and parts[1] == "indexed" and item:
                lines[index] = f"{parts[0]}\t{item['status']}\t{item['date']}"
                changed += 1
        args.file.write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"Updated {changed}/{len(targets)} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
