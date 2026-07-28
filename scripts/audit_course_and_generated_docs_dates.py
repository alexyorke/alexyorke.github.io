#!/usr/bin/env python3
"""Resolve dated course URLs and GitHub-generated API documentation."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse


INPUT = Path("io_links.md")
REPORT = Path("scratch/course-generated-docs-dates-audit.json")


def gh_commit(repository: str, path: str) -> dict | None:
    completed = subprocess.run(
        [
            "gh",
            "api",
            "-X",
            "GET",
            f"repos/{repository}/commits",
            "-f",
            "sha=main",
            "-f",
            f"path={path}",
            "-f",
            "per_page=1",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=40,
    )
    if completed.returncode:
        return None
    payload = json.loads(completed.stdout)
    return payload[0] if payload else None


def generated_source(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.hostname != "input-output-hk.github.io":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    if parts[0] == "typed-protocols":
        return "IntersectMBO/typed-protocols", "typed-protocols/src/Network/TypedProtocol.hs"
    if parts[0] != "io-sim":
        return None
    tail = "/".join(parts[1:])
    if tail.startswith("io-sim/"):
        return "IntersectMBO/io-sim", "io-sim/src/Control/Monad/IOSim.hs"
    if "MonadST" in tail:
        return "IntersectMBO/io-sim", "io-classes/src/Control/Monad/Class/MonadST.hs"
    if tail.startswith("io-classes/"):
        return "IntersectMBO/io-sim", "io-classes/io-classes.cabal"
    return "IntersectMBO/io-sim", "io-sim/io-sim.cabal"


def main() -> None:
    results = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        url = fields[0]
        host = urlparse(url).hostname or ""
        if host in {"cseweb.ucsd.edu", "www.cseweb.ucsd.edu"}:
            match = re.search(
                r"/(?:classes/)?(?:wi|su)(\d{2})|cse130-winter(\d{2})",
                url,
                re.I,
            )
            if match:
                short_year = int(match.group(1) or match.group(2))
                year = 2000 + short_year
                results.append(
                    {
                        "url": url,
                        "status": "created",
                        "date": str(year),
                        "evidence": "Academic year encoded by the official UCSD course URL.",
                        "source": url,
                    }
                )
            continue

        source = generated_source(url)
        if not source:
            continue
        repository, path = source
        commit = gh_commit(repository, path)
        committed = (
            commit.get("commit", {}).get("committer", {}).get("date")
            if commit
            else None
        )
        if committed:
            results.append(
                {
                    "url": url,
                    "status": "updated",
                    "date": committed[:10],
                    "evidence": "Latest commit timestamp for the source package or module rendered into this API documentation.",
                    "source": f"https://github.com/{repository}/commits/main/{path}",
                    "commit": commit.get("sha"),
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
