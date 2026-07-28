#!/usr/bin/env python3
"""Resolve remaining GitLab repository, wiki, and tagged-file dates."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import quote, urlparse

import requests


INPUT = Path("io_links.md")
REPORT = Path("scratch/remaining-gitlab-date-audit.json")
WIKI_REPO = Path("tmp/ghc-wiki-date-audit")


def git_date(*args: str) -> tuple[str, str]:
    output = subprocess.check_output(
        ["git", "-C", str(WIKI_REPO), *args], text=True
    ).strip()
    commit, date = output.split(maxsplit=1)
    return commit, date[:10]


def main() -> None:
    indexed = {
        fields[0]
        for line in INPUT.read_text(encoding="utf-8").splitlines()
        if len(fields := line.split("\t")) == 3 and fields[1] == "indexed"
    }
    results: list[dict] = []
    session = requests.Session()

    for url in sorted(indexed):
        parsed = urlparse(url)
        if parsed.netloc.lower() == "gitlab.com":
            project = "/".join(parsed.path.strip("/").split("/")[:2])
            response = session.get(
                f"https://gitlab.com/api/v4/projects/{quote(project, safe='')}",
                timeout=30,
            )
            if response.ok and response.json().get("created_at"):
                node = response.json()
                results.append(
                    {
                        "url": url,
                        "status": "created",
                        "date": node["created_at"][:10],
                        "source": response.url,
                        "evidence": f"GitLab project {node['id']} created_at",
                    }
                )

    wiki_urls = {
        "https://gitlab.haskell.org/ghc/ghc/-/wikis/linear-types/history": (
            "linear-types.md",
            None,
        ),
        "https://gitlab.haskell.org/ghc/ghc/-/wikis/status/may14/diff?version_id=2c17909462e87cf4dd6bfa587933b47162cf747d&w=1": (
            None,
            "2c17909462e87cf4dd6bfa587933b47162cf747d",
        ),
    }
    for url, (path, commit) in wiki_urls.items():
        if url not in indexed:
            continue
        if commit:
            resolved_commit, date = git_date(
                "show", "-s", "--format=%H %cI", commit
            )
        else:
            resolved_commit, date = git_date(
                "log", "--all", "-1", "--format=%H %cI", "--", path
            )
        results.append(
            {
                "url": url,
                "status": "updated",
                "date": date,
                "source": "https://gitlab.haskell.org/ghc/ghc.wiki.git",
                "evidence": f"wiki source commit {resolved_commit}",
            }
        )

    minio_url = (
        "https://gitlab.ifi.lmu.de/uni2work/haskell/minio-hs/-/blob/"
        "v1.5.1/minio-hs.cabal?ref_type=tags"
    )
    if minio_url in indexed:
        api_url = (
            "https://gitlab.ifi.lmu.de/api/v4/projects/"
            "uni2work%2Fhaskell%2Fminio-hs/repository/commits"
        )
        response = session.get(
            api_url,
            params={"path": "minio-hs.cabal", "ref_name": "v1.5.1", "per_page": 1},
            timeout=30,
        )
        commits = response.json() if response.ok else []
        if commits:
            results.append(
                {
                    "url": minio_url,
                    "status": "updated",
                    "date": commits[0]["created_at"][:10],
                    "source": response.url,
                    "evidence": f"latest tagged-file commit {commits[0]['id']}",
                }
            )

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(results, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"resolved={len(results)}")


if __name__ == "__main__":
    main()
