#!/usr/bin/env python3
"""Resolve remaining Hackage package URLs from the immutable package index."""

from __future__ import annotations

import json
import re
import tarfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse


INPUT = Path("io_links.md")
INDEX = Path("tmp/hackage-01-index.tar.gz")
REPORT = Path("scratch/hackage-index-dates-audit.json")
HOSTS = {
    "hackage.haskell.org",
    "hackage-origin.haskell.org",
    "hackage-content.haskell.org",
    "hackage-content-origin.haskell.org",
}


def main() -> None:
    uploads: dict[str, dict[str, int]] = defaultdict(dict)
    with tarfile.open(INDEX, "r:gz") as archive:
        for member in archive:
            match = re.fullmatch(r"([^/]+)/([^/]+)/[^/]+\.cabal", member.name)
            if match:
                package, version = match.groups()
                uploads[package][version] = max(
                    member.mtime, uploads[package].get(version, 0)
                )
    package_names = {package.casefold(): package for package in uploads}

    results = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        url = fields[0]
        parsed = urlparse(url)
        if parsed.hostname not in HOSTS:
            continue
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        try:
            package_index = parts.index("package")
            identifier = parts[package_index + 1]
        except (ValueError, IndexError):
            results.append(
                {
                    "url": url,
                    "unresolved_reason": "Hackage index, search, tag, or API page is not a package artifact.",
                }
            )
            continue

        identifier = re.sub(r"(?:\.tar\.gz|\.html)$", "", identifier)
        package = package_names.get(identifier.casefold())
        version = None
        if package is None:
            matches = [
                (name, candidate_version)
                for name, versions in uploads.items()
                for candidate_version in versions
                if identifier.casefold() == f"{name}-{candidate_version}".casefold()
            ]
            if matches:
                package, version = matches[0]
        if package is None:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": f"Package identifier {identifier!r} is absent from the Hackage index.",
                }
            )
            continue

        versions = uploads[package]
        timestamp = versions[version] if version else max(versions.values())
        value = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
        results.append(
            {
                "url": url,
                "status": "uploaded" if version else "updated",
                "date": value,
                "evidence": (
                    "Upload timestamp in Hackage 01-index.tar.gz for "
                    + (f"{package}-{version}." if version else f"the latest {package} release.")
                ),
                "source": "https://hackage.haskell.org/01-index.tar.gz",
                "package": package,
                "version": version,
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
