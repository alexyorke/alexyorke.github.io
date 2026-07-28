#!/usr/bin/env python3
"""Audit currently indexed GitHub repository and file links via GitHub API."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

INPUT = Path("io_links.md")
RAW = Path("scratch/github-dates-continuation-raw.json")
REPORT = Path("scratch/github-dates-continuation-audit.json")


def gh_get(endpoint: str, fields: dict[str, str] | None = None) -> tuple[int, object]:
    command = ["gh", "api", "-X", "GET", endpoint]
    for key, value in (fields or {}).items():
        command.extend(["-f", f"{key}={value}"])
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", timeout=40
    )
    body = completed.stdout or completed.stderr
    try:
        payload: object = json.loads(body)
    except json.JSONDecodeError:
        payload = body
    return completed.returncode, payload


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        parsed = urlparse(fields[0])
        if parsed.hostname == "github.com":
            targets.append(fields[0])

    raw_records = []
    results = []
    for index, url in enumerate(targets, 1):
        parts = [unquote(part) for part in urlparse(url).path.split("/") if part]
        if len(parts) < 2 or parts[0] == "topics":
            results.append(
                {
                    "url": url,
                    "unresolved_reason": "Mutable GitHub topic/index page has no single creation date.",
                }
            )
            continue

        owner, repository = parts[:2]
        repo_endpoint = f"repos/{owner}/{repository}"
        repo_status, repo = gh_get(repo_endpoint)
        raw_item = {
            "url": url,
            "repo_endpoint": f"https://api.github.com/{repo_endpoint}",
            "repo_status": repo_status,
            "repo_body": repo,
        }
        if repo_status != 0 or not isinstance(repo, dict):
            raw_records.append(raw_item)
            results.append(
                {
                    "url": url,
                    "unresolved_reason": f"GitHub repository API command exit {repo_status}.",
                    "source": raw_item["repo_endpoint"],
                }
            )
            continue

        if len(parts) >= 5 and parts[2] == "blob":
            branch = parts[3]
            path = "/".join(parts[4:])
            commit_endpoint = f"repos/{owner}/{repository}/commits"
            commit_status, commits = gh_get(
                commit_endpoint,
                {"sha": branch, "path": path, "per_page": "1"},
            )
            raw_item.update(
                {
                    "commit_endpoint": f"https://api.github.com/{commit_endpoint}?sha={branch}&path={path}&per_page=1",
                    "commit_status": commit_status,
                    "commit_body": commits,
                }
            )
            if commit_status == 0 and isinstance(commits, list) and commits:
                commit = commits[0]
                value = commit["commit"]["committer"]["date"][:10]
                results.append(
                    {
                        "url": url,
                        "status": "updated",
                        "date": value,
                        "evidence": "GitHub API latest commit date for the linked branch-relative file.",
                        "source": raw_item["commit_endpoint"],
                        "repository": repo.get("full_name"),
                        "commit": commit.get("sha"),
                    }
                )
            else:
                results.append(
                    {
                        "url": url,
                        "unresolved_reason": (
                            f"GitHub file-commit API command exit "
                            f"{commit_status} or no commits."
                        ),
                        "source": raw_item["commit_endpoint"],
                    }
                )
        else:
            created_at = repo.get("created_at")
            if created_at:
                results.append(
                    {
                        "url": url,
                        "status": "created",
                        "date": created_at[:10],
                        "evidence": "GitHub repository API created_at timestamp.",
                        "source": repo.get("html_url", raw_item["repo_endpoint"]),
                        "repository": repo.get("full_name"),
                    }
                )
            else:
                results.append(
                    {
                        "url": url,
                        "unresolved_reason": "GitHub repository API has no created_at timestamp.",
                        "source": raw_item["repo_endpoint"],
                    }
                )
        raw_records.append(raw_item)
        print(f"{index}/{len(targets)} {url}", flush=True)

    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(
        json.dumps({"records": raw_records}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report = {
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
