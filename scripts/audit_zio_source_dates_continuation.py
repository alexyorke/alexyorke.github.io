#!/usr/bin/env python3
"""Audit a bounded slice of indexed zio.dev pages via source commit dates."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


INPUT = Path("io_links.md")
RAW = Path("scratch/zio-source-dates-continuation-raw.json")
REPORT = Path("scratch/zio-source-dates-continuation-audit.json")
EDIT_RE = re.compile(
    r"https://github\.com/([^/]+)/([^/]+)/edit/([^\"'< ]+)", re.IGNORECASE
)


def source_parts(edit_tail: str) -> tuple[str, str] | None:
    tail = unquote(edit_tail)
    for marker in ("/docs/", "/website/", "/site/"):
        if marker in tail:
            branch, suffix = tail.split(marker, 1)
            return branch, f"{marker.strip('/')}/{suffix}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum rows to audit; zero audits every remaining zio.dev row.",
    )
    args = parser.parse_args()

    all_targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if (
            len(fields) == 3
            and fields[1] == "indexed"
            and urlparse(fields[0]).hostname == "zio.dev"
        ):
            all_targets.append(fields[0])
    targets = all_targets[: args.limit] if args.limit else all_targets

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "User-Agent": "io-links-date-audit/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    raw_records = []
    results = []
    for index, url in enumerate(targets, 1):
        page_response = session.get(url, timeout=40)
        edit_match = EDIT_RE.search(page_response.text)
        raw_item = {
            "url": url,
            "page_status": page_response.status_code,
            "edit_url": edit_match.group(0) if edit_match else None,
        }
        if page_response.status_code != 200 or not edit_match:
            raw_records.append(raw_item)
            results.append(
                {
                    "url": url,
                    "unresolved_reason": (
                        f"zio.dev HTTP {page_response.status_code} has no source edit link."
                    ),
                    "source": url,
                }
            )
            continue
        owner, repository, edit_tail = edit_match.groups()
        parsed_source = source_parts(edit_tail)
        if not parsed_source:
            raw_records.append(raw_item)
            results.append(
                {
                    "url": url,
                    "unresolved_reason": "Could not separate source branch and file path.",
                    "source": edit_match.group(0),
                }
            )
            continue
        branch, path = parsed_source
        endpoint = f"repos/{owner}/{repository}/commits"
        command = [
            "gh",
            "api",
            "-X",
            "GET",
            endpoint,
            "-f",
            f"sha={branch}",
            "-f",
            f"path={path}",
            "-f",
            "per_page=1",
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", timeout=40
        )
        try:
            payload = json.loads(completed.stdout) if completed.stdout else completed.stderr
        except json.JSONDecodeError:
            payload = completed.stdout or completed.stderr
        commit_status = 200 if completed.returncode == 0 else completed.returncode
        raw_item.update(
            {
                "branch": branch,
                "path": path,
                "commit_url": f"https://api.github.com/{endpoint}?sha={branch}&path={path}&per_page=1",
                "commit_status": commit_status,
                "commit_body": payload,
            }
        )
        raw_records.append(raw_item)
        if (
            completed.returncode == 0
            and isinstance(payload, list)
            and payload
        ):
            commit = payload[0]
            committed = commit.get("commit", {}).get("committer", {}).get("date")
            if committed:
                results.append(
                    {
                        "url": url,
                        "status": "updated",
                        "date": committed[:10],
                        "evidence": "Latest GitHub commit timestamp for the documentation source file linked by Edit this page.",
                        "source": raw_item["commit_url"],
                        "commit": commit.get("sha"),
                    }
                )
            else:
                results.append(
                    {
                        "url": url,
                        "unresolved_reason": "Latest source commit has no committer date.",
                        "source": raw_item["commit_url"],
                    }
                )
        else:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": (
                        f"GitHub commits API command exit {completed.returncode} "
                        "or no source-file commits."
                    ),
                    "source": raw_item["commit_url"],
                }
            )
        print(f"{index}/{len(targets)} {url}", flush=True)

    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(
        json.dumps({"records": raw_records}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report = {
        "discovered_count": len(all_targets),
        "target_count": len(targets),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
        "results": results,
    }
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in report.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()
