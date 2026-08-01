#!/usr/bin/env python3
"""Find and optionally remove byte-identical cross-domain document mirrors."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests


DOCUMENT = re.compile(r"\.(?:pdf|ps|dvi|docx?|pptx?)(?:\.gz)?$", re.I)
COPY_SUFFIX = re.compile(
    r"(?:[-_.](?:copy|final|revised|revision|rev|v\d+|version\d+|\d+))+$", re.I
)
MAX_BYTES = 50 * 1024 * 1024


def basename(url: str) -> str | None:
    value = unquote(urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]).casefold()
    if not DOCUMENT.search(value):
        return None
    stem = DOCUMENT.sub("", value)
    stem = COPY_SUFFIX.sub("", stem)
    stem = re.sub(r"[^a-z0-9]+", "", stem)
    return stem if len(stem) >= 6 else None


def fuzzy_candidate_names(names: set[str]) -> set[str]:
    """Return names in conservative high-similarity pairs.

    Prefix/suffix buckets keep this bounded while allowing small filename
    revisions that exact normalization cannot collapse.
    """
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for name in names:
        if len(name) >= 10:
            buckets[(name[:5], "prefix")].append(name)
            buckets[(name[-5:], "suffix")].append(name)
    matched: set[str] = set()
    compared: set[tuple[str, str]] = set()
    for group in buckets.values():
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                pair = tuple(sorted((left, right)))
                if pair in compared:
                    continue
                compared.add(pair)
                length_ratio = min(len(left), len(right)) / max(len(left), len(right))
                if length_ratio >= 0.82 and SequenceMatcher(None, left, right).ratio() >= 0.9:
                    matched.update(pair)
    return matched


def fetch_digest(url: str) -> dict[str, object]:
    try:
        with requests.get(
            url,
            headers={"User-Agent": "io-links-duplicate-audit/1.0"},
            stream=True,
            timeout=(10, 30),
            allow_redirects=True,
        ) as response:
            content_type = response.headers.get("content-type", "").casefold()
            if response.status_code != 200:
                return {"status": response.status_code, "error": "HTTP status"}
            if "text/html" in content_type:
                return {"status": response.status_code, "error": "HTML response"}
            digest = hashlib.sha256()
            size = 0
            prefix = b""
            for chunk in response.iter_content(1024 * 128):
                if not chunk:
                    continue
                if len(prefix) < 512:
                    prefix += chunk[: 512 - len(prefix)]
                size += len(chunk)
                if size > MAX_BYTES:
                    return {"status": response.status_code, "error": "too large"}
                digest.update(chunk)
            if size < 1000 or b"<html" in prefix.lower():
                return {"status": response.status_code, "error": "invalid document"}
            return {
                "status": response.status_code,
                "sha256": digest.hexdigest(),
                "size": size,
                "final_url": response.url,
            }
    except requests.RequestException as exc:
        return {"status": None, "error": type(exc).__name__}


def url_rank(row: list[str]) -> tuple[int, int, int, int]:
    parsed = urlsplit(row[0])
    host = (parsed.hostname or "").casefold()
    mirror_penalty = int(
        not any(token in host for token in ("archive", "mirror", "scholar"))
    )
    return (
        int(parsed.scheme == "https"),
        mirror_penalty,
        int(not host.startswith("www.")),
        -len(row[0]),
    )


def metadata_rank(row: list[str]) -> tuple[int, int, str]:
    rank = {
        "publication": 6,
        "published": 6,
        "released": 5,
        "uploaded": 5,
        "authored": 5,
        "created": 3,
        "updated": 2,
        "modified": 2,
        "archived": 1,
        "accessed": 0,
    }.get(row[1], 1)
    return rank, row[2].count("-"), row[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--cache", type=Path, default=Path("scratch/document-content-hashes.json")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/document-content-duplicates.json")
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    title = next((line for line in lines if line.startswith("# ")), "# IO Monad Links")
    rows = [line.split("\t") for line in lines if len(line.split("\t")) == 3]
    by_name: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        key = basename(row[0])
        if key:
            by_name[key].append(row)
    fuzzy_names = fuzzy_candidate_names(set(by_name))
    candidates = {
        row[0]
        for group in by_name.values()
        if len(group) > 1
        for row in group
    }
    candidates.update(
        row[0] for name in fuzzy_names for row in by_name[name]
    )

    cache = json.loads(args.cache.read_text(encoding="utf-8")) if args.cache.exists() else {}
    pending = sorted(candidates - cache.keys())
    if pending:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(fetch_digest, url): url for url in pending}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    cache[url] = future.result()
                except Exception as exc:  # Preserve the rest of a long audit batch.
                    cache[url] = {"status": None, "error": type(exc).__name__}
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        args.cache.write_text(
            json.dumps(cache, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    by_hash: dict[tuple[str, int], list[list[str]]] = defaultdict(list)
    for row in rows:
        item = cache.get(row[0], {})
        if item.get("sha256") and item.get("size"):
            by_hash[(item["sha256"], item["size"])].append(row)
    groups = [group for group in by_hash.values() if len(group) > 1]

    removed: dict[str, str] = {}
    replacements: dict[str, list[str]] = {}
    report_groups = []
    for group in groups:
        url_winner = max(group, key=url_rank)
        metadata = max(group, key=metadata_rank)
        winner = [url_winner[0], metadata[1], metadata[2]]
        replacements[url_winner[0]] = winner
        for row in group:
            if row[0] != url_winner[0]:
                removed[row[0]] = url_winner[0]
        report_groups.append(
            {
                "kept": winner,
                "removed": [row for row in group if row[0] != url_winner[0]],
                "sha256": cache[url_winner[0]]["sha256"],
                "size": cache[url_winner[0]]["size"],
            }
        )

    report = {
        "candidate_urls": len(candidates),
        "fuzzy_candidate_names": len(fuzzy_names),
        "fetched_now": len(pending),
        "hashed_documents": sum(
            bool(cache.get(url, {}).get("sha256")) for url in candidates
        ),
        "duplicate_groups": len(groups),
        "removed_records": len(removed),
        "groups": report_groups,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if args.apply and removed:
        output = []
        for row in rows:
            if row[0] in removed:
                continue
            output.append(replacements.get(row[0], row))
        output.sort(key=lambda row: row[2])
        args.file.write_text(
            "\n".join([title, *("\t".join(row) for row in output)]) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print({key: value for key, value in report.items() if key != "groups"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
