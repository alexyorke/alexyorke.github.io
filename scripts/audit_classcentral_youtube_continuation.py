#!/usr/bin/env python3
"""Resolve current Class Central YouTube-course rows to exact video upload dates."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse


INPUT = Path("io_links.md")
CACHE = Path("scratch/classcentral-youtube-continuation-raw.json")


def query_from_url(url: str) -> str:
    slug = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
    slug = re.sub(r"^\d+-", "", slug)
    slug = re.sub(r"-\d+$", "", slug)
    slug = re.sub(r"^youtube-", "", slug)
    slug = re.sub(r"^index\.php$", "", slug)
    return slug.replace("-", " ")


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        url = fields[0]
        parsed = urlparse(url)
        if parsed.hostname != "www.classcentral.com" or "/course/" not in parsed.path:
            continue
        if "youtube-" not in parsed.path:
            continue
        targets.append(url)

    payload = {"target_count": len(targets), "results": []}
    for index, url in enumerate(targets, 1):
        query = query_from_url(url)
        completed = subprocess.run(
            [
                "yt-dlp",
                "--dump-single-json",
                "--skip-download",
                "--no-warnings",
                f"ytsearch3:{query}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        record = {
            "url": url,
            "query": query,
            "returncode": completed.returncode,
            "stderr": completed.stderr.strip(),
            "candidates": [],
        }
        if completed.returncode == 0:
            search = json.loads(completed.stdout)
            for item in search.get("entries") or []:
                record["candidates"].append(
                    {
                        key: item.get(key)
                        for key in (
                            "id",
                            "title",
                            "upload_date",
                            "timestamp",
                            "channel",
                            "channel_id",
                            "webpage_url",
                            "duration",
                        )
                    }
                )
        payload["results"].append(record)
        print(
            f"{index}/{len(targets)} {query}: "
            f"{len(record['candidates'])} candidates",
            flush=True,
        )

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
