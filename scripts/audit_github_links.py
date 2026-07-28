#!/usr/bin/env python3
"""Resolve indexed GitHub and codeload links through authenticated gh API reads."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse


def gh_api(endpoint: str) -> tuple[object | None, str | None]:
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if result.returncode:
        return None, result.stderr.strip()[:500]
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError:
        return None, "invalid GitHub API response"


def inspect(url: str) -> dict:
    parsed = urlparse(url)
    parts = unquote(parsed.path).strip("/").split("/")
    item = {
        "url": url,
        "status": None,
        "date": None,
        "source": "github-api",
    }
    if parsed.netloc.lower() == "codeload.github.com" and len(parts) >= 5:
        owner, repo = parts[0], parts[1]
        marker = parts.index("heads") if "heads" in parts else -1
        branch = parts[marker + 1] if marker >= 0 and len(parts) > marker + 1 else None
        if branch:
            node, error = gh_api(f"repos/{owner}/{repo}/commits/{branch}")
            if isinstance(node, dict):
                timestamp = ((node.get("commit") or {}).get("author") or {}).get("date")
                if timestamp:
                    item.update(
                        status="updated",
                        date=timestamp[:10],
                        evidence=f"{owner}/{repo} branch {branch} head {node.get('sha')}",
                    )
            item["error"] = error
        return item

    if parsed.netloc.lower() != "github.com" or not parts:
        return item
    if parts[0] == "topics":
        item["error"] = "topic pages have no creation-date API"
        return item
    if len(parts) == 1:
        node, error = gh_api(f"users/{parts[0]}")
        if isinstance(node, dict) and node.get("created_at"):
            item.update(
                status="created",
                date=node["created_at"][:10],
                evidence=f"{node.get('type', 'account')} creation timestamp",
            )
        item["error"] = error
        return item

    owner, repo = parts[0], parts[1]
    if repo.endswith(".wiki"):
        repo = repo.removesuffix(".wiki")
    if len(parts) >= 5 and parts[2] in {"blob", "raw"}:
        path = "/".join(parts[4:])
        node, error = gh_api(
            f"repos/{owner}/{repo}/commits?path={path}&per_page=100"
        )
        if isinstance(node, list) and node:
            oldest = node[-1]
            timestamp = ((oldest.get("commit") or {}).get("author") or {}).get("date")
            if timestamp:
                item.update(
                    status="created",
                    date=timestamp[:10],
                    evidence=f"oldest returned commit for {path}: {oldest.get('sha')}",
                )
        item["error"] = error
        return item

    node, error = gh_api(f"repos/{owner}/{repo}")
    if isinstance(node, dict) and node.get("created_at"):
        item.update(
            status="created",
            date=node["created_at"][:10],
            evidence=f"repository {owner}/{repo} creation timestamp",
        )
    item["error"] = error
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/github-link-audit.json")
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    urls = []
    for line in lines:
        parts = line.split("\t")
        if (
            len(parts) == 3
            and parts[1] == "indexed"
            and urlparse(parts[0]).netloc.lower()
            in {"github.com", "codeload.github.com"}
        ):
            urls.append(parts[0])
    results = []
    for count, url in enumerate(urls, 1):
        results.append(inspect(url))
        print(
            f"{count}/{len(urls)} checked; "
            f"{sum(bool(item.get('date')) for item in results)} resolved",
            flush=True,
        )
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
        print(f"Updated {changed}/{len(urls)} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
