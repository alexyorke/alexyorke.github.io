#!/usr/bin/env python3
"""Resolve Debian Sources links from version changelog timestamps."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests
from dateutil import parser as date_parser


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/debian-sources-audit.json")
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    targets: dict[str, tuple[str, str | None]] = {}
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if parsed.netloc.lower() != "sources.debian.org":
            continue
        match = re.match(r"/src/([^/]+)(?:/([^/]+))?", unquote(parsed.path))
        if match:
            targets[parts[0]] = match.groups()

    session = requests.Session()
    metadata: dict[tuple[str, str | None], dict] = {}
    for package, requested_version in sorted(
        set(targets.values()), key=lambda item: (item[0], item[1] or "")
    ):
        version = requested_version
        if not version:
            response = session.get(
                f"https://sources.debian.org/api/src/{quote(package)}/", timeout=30
            )
            versions = response.json().get("versions", []) if response.ok else []
            version = versions[0].get("version") if versions else None
        item = {
            "package": package,
            "requested_version": requested_version,
            "version": version,
            "status": None,
            "date": None,
            "source": "debian-changelog",
        }
        if version:
            info_response = session.get(
                f"https://sources.debian.org/api/src/{quote(package)}/"
                f"{quote(version, safe='+~.-:')}/",
                timeout=30,
            )
            info = info_response.json() if info_response.ok else {}
            area = (info.get("pkg_infos") or {}).get("area")
            if area:
                changelog_url = (
                    f"https://sources.debian.org/data/{quote(area)}/"
                    f"{quote(package[0].lower())}/{quote(package)}/"
                    f"{quote(version, safe='+~.-:')}/debian/changelog"
                )
                changelog_response = session.get(changelog_url, timeout=30)
                item.update(
                    area=area,
                    changelog_url=changelog_url,
                    http_status=changelog_response.status_code,
                )
                if changelog_response.ok:
                    match = re.search(
                        r"^ -- .+?  (.+)$", changelog_response.text, re.M
                    )
                    if match:
                        try:
                            value = date_parser.parse(match.group(1)).date().isoformat()
                        except (OverflowError, ValueError):
                            value = None
                        if value:
                            item.update(
                                status="uploaded",
                                date=value,
                                evidence=match.group(0).strip(),
                            )
        metadata[(package, requested_version)] = item

    results = []
    for url, key in targets.items():
        results.append({"url": url, **metadata[key]})
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
