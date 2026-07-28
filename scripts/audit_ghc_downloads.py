#!/usr/bin/env python3
"""Replace indexed dates on versioned GHC documentation with release dates."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


PROJECT = "ghc%2Fghc"
API = f"https://gitlab.haskell.org/api/v4/projects/{PROJECT}/repository/tags/"
USER_AGENT = "io-links-date-audit/1.0"
VERSION_RE = re.compile(r"downloads\.haskell\.org/(?:~?ghc)/(\d+(?:\.\d+)+)/")

# These releases predate the tags available from the current GHC GitLab
# repository. Their dates come from official GHC release pages.
LEGACY_RELEASES = {
    "6.0": {
        "date": "2003-05-28",
        "source": "https://www.haskell.org/ghc/download_ghc_600",
    },
    "6.2": {
        "date": "2003-12-16",
        "source": "https://www.haskell.org/ghc/download_ghc_62.html",
    },
    "6.8.2": {
        "date": "2007-12-12",
        "source": "https://www.haskell.org/ghc/download_ghc_682.html",
    },
}


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def release_for(version: str) -> dict | None:
    if version in LEGACY_RELEASES:
        return {
            "version": version,
            "date": LEGACY_RELEASES[version]["date"],
            "source": LEGACY_RELEASES[version]["source"],
            "evidence": "official-release-page",
        }

    tag = f"ghc-{version}-release"
    url = API + urllib.parse.quote(tag, safe="")
    try:
        payload = get_json(url)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise

    timestamp = payload.get("created_at")
    evidence = "release-tag-created"
    if not timestamp:
        timestamp = payload.get("commit", {}).get("committed_date")
        evidence = "release-tag-commit"
    if not timestamp:
        return None

    return {
        "version": version,
        "date": datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date().isoformat(),
        "source": payload.get("web_url")
        or f"https://gitlab.haskell.org/ghc/ghc/-/tags/{tag}",
        "evidence": evidence,
        "tag": tag,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/ghc-download-audit.json")
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    lines = args.input.read_text(encoding="utf-8").splitlines()
    targets: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        match = VERSION_RE.search(fields[0])
        if match and match.group(1) not in {"9.12"}:
            targets.append((index, fields[0], match.group(1)))

    releases = {
        version: release_for(version)
        for version in sorted({version for _, _, version in targets})
    }
    resolved = []
    unresolved = []
    for index, url, version in targets:
        release = releases[version]
        if not release:
            unresolved.append({"url": url, "version": version})
            continue
        resolved.append({"url": url, **release})
        if args.apply:
            lines[index] = f"{url}\tpublished\t{release['date']}"

    report = {
        "target_count": len(targets),
        "resolved_count": len(resolved),
        "unresolved_count": len(unresolved),
        "resolved": resolved,
        "unresolved": unresolved,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if args.apply:
        args.input.write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
    print(json.dumps({key: report[key] for key in report if key.endswith("_count")}))


if __name__ == "__main__":
    main()
