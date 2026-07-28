#!/usr/bin/env python3
"""Resolve YouTube playlist/channel pages through yt-dlp modification metadata."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse


INPUT = Path("io_links.md")
REPORT = Path("scratch/youtube-modified-dates-audit.json")


def audit(url: str) -> dict:
    completed = subprocess.run(
        [
            "yt-dlp",
            "--flat-playlist",
            "--dump-single-json",
            "--skip-download",
            "--no-warnings",
            url,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if completed.returncode:
        return {
            "url": url,
            "unresolved_reason": completed.stderr.strip()[-500:],
            "source": url,
        }
    payload = json.loads(completed.stdout)
    raw_date = payload.get("modified_date")
    if not re.fullmatch(r"\d{8}", str(raw_date or "")):
        return {
            "url": url,
            "unresolved_reason": "yt-dlp metadata has no playlist/channel modified_date.",
            "source": url,
        }
    value = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    return {
        "url": url,
        "status": "modified",
        "date": value,
        "evidence": "YouTube playlist/channel modified_date exposed by yt-dlp.",
        "source": url,
        "title": payload.get("title"),
        "youtube_id": payload.get("id"),
    }


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        if urlparse(fields[0]).hostname in {"youtube.com", "www.youtube.com"}:
            targets.append(fields[0])
    results = [audit(url) for url in targets]
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
