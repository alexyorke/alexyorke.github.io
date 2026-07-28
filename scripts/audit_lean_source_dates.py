#!/usr/bin/env python3
"""Resolve Lean documentation dates from their maintained GitHub sources."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse


INPUT = Path("io_links.md")
REPORT = Path("scratch/lean-source-dates-audit.json")


def gh_commit(repository: str, branch: str, path: str) -> dict | None:
    completed = subprocess.run(
        [
            "gh",
            "api",
            "-X",
            "GET",
            f"repos/{repository}/commits",
            "-f",
            f"sha={branch}",
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


def source_for(url: str) -> tuple[str, str, str] | None:
    path = urlparse(url).path
    if "functional_programming_in_lean" in path:
        tail = path.split("functional_programming_in_lean", 1)[1]
        mapping = {
            "The-IO-Monad": "book/FPLean/Monads/IO.lean",
            "The-Monad-Type-Class": "book/FPLean/Monads/Class.lean",
            "do--Notation-for-Monads": "book/FPLean/Monads/Do.lean",
            "Summary": "book/FPLean/Monads/Summary.lean",
            "One-API___-Many-Applications": "book/FPLean/Monads/Arithmetic.lean",
            "Introduction": "book/FPLean/Intro.lean",
        }
        for marker, source in mapping.items():
            if marker in tail:
                return "leanprover/fp-lean", "master", source
        if "/Monads" in tail or tail.rstrip("/").endswith("monads.html"):
            return "leanprover/fp-lean", "master", "book/FPLean/Monads.lean"
        return "leanprover/fp-lean", "master", "book/FPLean.lean"

    if "/doc/reference/" in path:
        branch = "main"
        if "/4.19.0-rc2/" in path:
            branch = "v4.19.0-rc2"
        tail = path.split("/doc/reference/", 1)[1]
        mapping = {
            "Files___-File-Handles___-and-Streams": "Manual/IO/Files.lean",
            "Tasks-and-Threads": "Manual/IO/Threads.lean",
            "Console-Output": "Manual/IO/Console.lean",
            "Mutable-References": "Manual/IO/Ref.lean",
            "Iterators": "Manual/Iterators.lean",
            "Varieties-of-Monads": "Manual/Monads/Zoo.lean",
            "Lifting-Monads": "Manual/Monads/Lift.lean",
            "mvcgen": "Tutorial/VCGen.lean",
        }
        for marker, source in mapping.items():
            if marker in tail:
                return "leanprover/reference-manual", branch, source
        if "/IO/" in f"/{tail}" or tail.rstrip("/").endswith("/IO"):
            return "leanprover/reference-manual", branch, "Manual/IO.lean"
        if "Functors" in tail or "Monads" in tail:
            return "leanprover/reference-manual", branch, "Manual/Monads.lean"
        return "leanprover/reference-manual", branch, "Manual.lean"

    if "/doc/tutorials/" in path:
        return "leanprover/reference-manual", "main", "TutorialMain.lean"
    return None


def main() -> None:
    results = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        url = fields[0]
        source = source_for(url)
        if not source:
            continue
        repository, branch, path = source
        commit = gh_commit(repository, branch, path)
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
                    "evidence": "Latest commit timestamp for the documentation source file.",
                    "source": f"https://github.com/{repository}/commits/{branch}/{path}",
                    "commit": commit.get("sha"),
                }
            )
        else:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": f"No commit found for {repository}:{branch}:{path}.",
                }
            )

    payload = {
        "target_count": len(results),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
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
