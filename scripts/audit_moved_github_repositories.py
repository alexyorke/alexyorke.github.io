#!/usr/bin/env python3
"""Resolve GitHub URLs whose repositories moved to a new owner or organization."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


INPUT = Path("io_links.md")
REPORT = Path("scratch/moved-github-repositories-audit.json")
MOVED = {
    "https://github.com/bluefin-haskell/bluefin": "tomjaguarpaw/bluefin",
    "https://github.com/eldritch-cookie/hedis-effectful": "scrive/hedis-effectful",
    "https://github.com/haskell/effectful": "haskell-effectful/effectful",
    "https://github.com/cjdev/monad-mock": "cjdev2/monad-mock",
    "https://github.com/mercury-haskell/io-sim": "IntersectMBO/io-sim",
    "https://github.com/Effekt-TS/effekt": "effekt-lang/effekt",
    "https://github.com/purescript/purescript-aff": "purescript-contrib/purescript-aff",
}


def gh_json(arguments: list[str]) -> object:
    completed = subprocess.run(
        ["gh", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=40,
        check=True,
    )
    return json.loads(completed.stdout)


def main() -> None:
    indexed = {
        line.split("\t")[0]
        for line in INPUT.read_text(encoding="utf-8").splitlines()
        if "\tindexed\t" in line
    }
    results = []
    for old_url, repository in MOVED.items():
        if old_url not in indexed:
            continue
        metadata = gh_json(
            [
                "repo",
                "view",
                repository,
                "--json",
                "createdAt,nameWithOwner,url",
            ]
        )
        results.append(
            {
                "url": old_url,
                "status": "created",
                "date": metadata["createdAt"][:10],
                "evidence": "GitHub created_at timestamp retained by the repository at its current owner.",
                "source": metadata["url"],
                "current_repository": metadata["nameWithOwner"],
            }
        )

    old_readme = "https://github.com/purescript/purescript-aff/blob/master/README.md"
    if old_readme in indexed:
        commits = gh_json(
            [
                "api",
                "-X",
                "GET",
                "repos/purescript-contrib/purescript-aff/commits",
                "-f",
                "sha=main",
                "-f",
                "path=README.md",
                "-f",
                "per_page=1",
            ]
        )
        commit = commits[0]
        results.append(
            {
                "url": old_readme,
                "status": "updated",
                "date": commit["commit"]["committer"]["date"][:10],
                "evidence": "Latest README commit after the repository moved to purescript-contrib.",
                "source": "https://github.com/purescript-contrib/purescript-aff/commits/main/README.md",
                "commit": commit["sha"],
            }
        )

    payload = {
        "target_count": len(results),
        "resolved_count": len(results),
        "unresolved_count": 0,
        "results": results,
    }
    REPORT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in payload.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()
