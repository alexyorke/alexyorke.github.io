#!/usr/bin/env python3
"""Resolve GHC GitLab issue, merge request, and file dates via its public API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests


def inspect(session: requests.Session, url: str) -> dict:
    parsed = urlparse(url)
    before, marker, after = unquote(parsed.path).partition("/-/")
    project = before.strip("/")
    segments = after.strip("/").split("/") if marker else []
    item = {"url": url, "status": None, "date": None, "source": "gitlab-api"}
    base = f"https://gitlab.haskell.org/api/v4/projects/{quote(project, safe='')}"
    if len(segments) >= 2 and segments[0] in {"issues", "merge_requests"}:
        response = session.get(f"{base}/{segments[0]}/{segments[1]}", timeout=30)
        item["http_status"] = response.status_code
        if response.ok:
            node = response.json()
            if node.get("created_at"):
                item.update(
                    status="created",
                    date=node["created_at"][:10],
                    evidence=f"{segments[0]} {segments[1]} created_at",
                )
        return item
    if len(segments) >= 3 and segments[0] == "blob":
        ref = segments[1]
        path = "/".join(segments[2:])
        if len(ref) == 40:
            response = session.get(f"{base}/repository/commits/{ref}", timeout=30)
            item["http_status"] = response.status_code
            if response.ok and response.json().get("created_at"):
                item.update(
                    status="created",
                    date=response.json()["created_at"][:10],
                    evidence=f"commit {ref}",
                )
        else:
            response = session.get(
                f"{base}/repository/commits",
                params={"path": path, "ref_name": ref, "per_page": 1},
                timeout=30,
            )
            item["http_status"] = response.status_code
            commits = response.json() if response.ok else []
            if isinstance(commits, list) and commits and commits[0].get("created_at"):
                item.update(
                    status="updated",
                    date=commits[0]["created_at"][:10],
                    evidence=f"latest {path} commit {commits[0].get('id')}",
                )
        return item
    item["error"] = "unsupported GitLab page type"
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/gitlab-link-audit.json")
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
            and urlparse(parts[0]).netloc.lower() == "gitlab.haskell.org"
        ):
            urls.append(parts[0])
    session = requests.Session()
    results = [inspect(session, url) for url in urls]
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
