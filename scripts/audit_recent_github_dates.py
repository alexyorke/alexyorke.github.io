#!/usr/bin/env python3
"""Audit GitHub dates within one week of 2026-07-28 using authoritative API data."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

INPUT = Path("io_links.md")
OUTPUT = Path("scratch/recent-github-date-audit.json")
START = "2026-07-21"
END = "2026-07-28"


def gh_get(endpoint: str, fields: dict[str, str] | None = None) -> object | None:
    command = ["gh", "api", "-X", "GET", endpoint]
    for key, value in (fields or {}).items():
        command.extend(["-f", f"{key}={value}"])
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", timeout=40
    )
    if completed.returncode:
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None


def main() -> None:
    targets: list[dict[str, str]] = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if (
            len(fields) == 3
            and START <= fields[2] <= END
            and urlparse(fields[0]).hostname
            in {"github.com", "raw.githubusercontent.com", "api.github.com"}
        ):
            targets.append({"url": fields[0], "old_status": fields[1], "old_date": fields[2]})

    repository_cache: dict[str, object | None] = {}
    results: list[dict[str, object]] = []
    for index, target in enumerate(targets, 1):
        url = target["url"]
        parsed = urlparse(url)
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        result: dict[str, object] = dict(target)
        if parsed.hostname == "raw.githubusercontent.com" and len(parts) >= 4:
            parts = [parts[0], parts[1], "raw", parts[2], *parts[3:]]
        elif parsed.hostname == "api.github.com" and len(parts) >= 4 and parts[0] == "repos":
            owner, repository = parts[1:3]
            if parts[3] == "contents":
                ref = "HEAD"
                path = "/".join(parts[4:])
                parts = [owner, repository, "raw", ref, path]
            else:
                parts = [owner, repository]
        if len(parts) < 2 or parts[0] in {"topics", "search"}:
            result["unresolved_reason"] = "Not a repository or file URL."
            results.append(result)
            continue

        owner, repository = parts[:2]
        repo_key = f"{owner}/{repository}"
        if repo_key not in repository_cache:
            repository_cache[repo_key] = gh_get(f"repos/{repo_key}")
        repo = repository_cache[repo_key]
        if not isinstance(repo, dict):
            result["unresolved_reason"] = "Repository API lookup failed."
        elif len(parts) >= 5 and parts[2] in {"blob", "raw"}:
            ref = parts[3]
            path = "/".join(parts[4:])
            commits = gh_get(
                f"repos/{repo_key}/commits",
                {"sha": ref, "path": path, "per_page": "1"},
            )
            if isinstance(commits, list) and commits:
                result.update(
                    {
                        "status": "updated",
                        "date": commits[0]["commit"]["committer"]["date"][:10],
                        "source": commits[0]["html_url"],
                        "evidence": "Latest commit affecting the linked file and ref.",
                    }
                )
            else:
                result["unresolved_reason"] = "File commit lookup failed or returned no commits."
        else:
            result.update(
                {
                    "status": "created",
                    "date": repo["created_at"][:10],
                    "source": repo["html_url"],
                    "evidence": "GitHub repository created_at timestamp.",
                }
            )
        results.append(result)
        if index % 25 == 0:
            print(f"{index}/{len(targets)}", flush=True)

    report = {
        "target_count": len(targets),
        "resolved_count": sum("date" in item for item in results),
        "changed_count": sum(
            item.get("date") != item["old_date"] or item.get("status") != item["old_status"]
            for item in results
            if "date" in item
        ),
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in report.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()
