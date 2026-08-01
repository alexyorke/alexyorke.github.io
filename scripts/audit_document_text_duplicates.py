#!/usr/bin/env python3
"""Remove document mirrors whose normalized text is at least 95% similar."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from audit_document_content_duplicates import basename, metadata_rank, url_rank


WORDS = re.compile(r"[a-z0-9]+")
MAX_BYTES = 50 * 1024 * 1024


def similar_name(left: str, right: str) -> bool:
    from difflib import SequenceMatcher

    length_ratio = min(len(left), len(right)) / max(len(left), len(right))
    return (
        len(left) >= 7
        and len(right) >= 7
        and length_ratio >= 0.5
        and (left[:1] == right[:1] or left[-1:] == right[-1:])
        and SequenceMatcher(None, left, right).ratio() >= 0.65
    )


def text_sample(url: str) -> dict[str, object]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "io-links-text-duplicate-audit/1.0"},
            timeout=(10, 40),
            allow_redirects=True,
        )
        if response.status_code != 200 or len(response.content) > MAX_BYTES:
            return {"error": f"HTTP {response.status_code}"}
        if not response.content.startswith(b"%PDF"):
            return {"error": "not PDF"}
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "input.pdf"
            txt = Path(directory) / "output.txt"
            pdf.write_bytes(response.content)
            result = subprocess.run(
                ["pdftotext", "-enc", "UTF-8", str(pdf), str(txt)],
                capture_output=True,
                timeout=20,
            )
            if result.returncode != 0 or not txt.exists():
                return {"error": "pdftotext"}
            words = WORDS.findall(txt.read_text(encoding="utf-8", errors="ignore").casefold())
        if len(words) < 100:
            return {"error": "too little text"}
        hashes: set[str] = set()
        for index in range(len(words) - 4):
            shingle = " ".join(words[index : index + 5]).encode()
            digest = hashlib.blake2b(shingle, digest_size=8).digest()
            if digest[0] < 16:  # Stable 1/16 sample of five-word shingles.
                hashes.add(digest.hex())
        return {"words": len(words), "sample": sorted(hashes)}
    except (requests.RequestException, subprocess.SubprocessError, OSError) as exc:
        return {"error": type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument("--cache", type=Path, default=Path("scratch/document-text-samples.json"))
    parser.add_argument("--report", type=Path, default=Path("scratch/document-text-duplicates.json"))
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    title = lines[0]
    rows = [line.split("\t") for line in lines[1:] if len(line.split("\t")) == 3]
    by_name: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        name = basename(row[0])
        if name:
            by_name[name].append(row)

    pairs: set[tuple[str, str]] = set()
    names = sorted(by_name)
    for index, left in enumerate(names):
        related = [left] if len(by_name[left]) > 1 else []
        related.extend(right for right in names[index + 1 :] if similar_name(left, right))
        for right in related:
            left_rows = by_name[left]
            right_rows = by_name[right]
            if left == right:
                for row_index, first in enumerate(left_rows):
                    for second in left_rows[row_index + 1 :]:
                        pairs.add(tuple(sorted((first[0], second[0]))))
            else:
                for first in left_rows:
                    for second in right_rows:
                        pairs.add(tuple(sorted((first[0], second[0]))))

    cache = json.loads(args.cache.read_text(encoding="utf-8")) if args.cache.exists() else {}
    current_urls = {row[0] for row in rows}
    postings: dict[str, list[str]] = defaultdict(list)
    for url, item in cache.items():
        if url in current_urls:
            for shingle in item.get("sample", []):
                postings[shingle].append(url)
    shared_counts: dict[tuple[str, str], int] = defaultdict(int)
    for posting in postings.values():
        if 1 < len(posting) <= 30:
            for index, left in enumerate(posting):
                for right in posting[index + 1 :]:
                    shared_counts[tuple(sorted((left, right)))] += 1
    pairs.update(pair for pair, count in shared_counts.items() if count >= 8)

    urls = {url for pair in pairs for url in pair}
    pending = sorted(urls - cache.keys())
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(text_sample, url): url for url in pending}
        for future in as_completed(futures):
            cache[futures[future]] = future.result()
            completed += 1
            if completed % 25 == 0:
                args.cache.parent.mkdir(parents=True, exist_ok=True)
                args.cache.write_text(json.dumps(cache, sort_keys=True) + "\n", encoding="utf-8")
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    args.cache.write_text(json.dumps(cache, sort_keys=True) + "\n", encoding="utf-8")

    parent: dict[str, str] = {url: url for url in urls}
    def find(url: str) -> str:
        while parent[url] != url:
            parent[url] = parent[parent[url]]
            url = parent[url]
        return url
    def union(left: str, right: str) -> None:
        parent[find(right)] = find(left)

    matches = []
    for left, right in sorted(pairs):
        a = set(cache.get(left, {}).get("sample", []))
        b = set(cache.get(right, {}).get("sample", []))
        if len(a) < 20 or len(b) < 20:
            continue
        overlap = len(a & b)
        containment = overlap / min(len(a), len(b))
        jaccard = overlap / len(a | b)
        if jaccard >= args.threshold:
            union(left, right)
            matches.append({"left": left, "right": right, "containment": containment, "jaccard": jaccard})

    row_by_url = {row[0]: row for row in rows}
    components: dict[str, list[list[str]]] = defaultdict(list)
    for url in urls:
        components[find(url)].append(row_by_url[url])
    duplicate_groups = [group for group in components.values() if len(group) > 1]
    removed: dict[str, str] = {}
    replacements: dict[str, list[str]] = {}
    for group in duplicate_groups:
        url_winner = max(group, key=url_rank)
        metadata = max(group, key=metadata_rank)
        replacements[url_winner[0]] = [url_winner[0], metadata[1], metadata[2]]
        for row in group:
            if row[0] != url_winner[0]:
                removed[row[0]] = url_winner[0]

    report = {
        "candidate_pairs": len(pairs), "candidate_urls": len(urls),
        "fetched_now": len(pending), "text_matches": len(matches),
        "duplicate_groups": len(duplicate_groups), "removed_records": len(removed),
        "matches": matches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.apply and removed:
        output = [replacements.get(row[0], row) for row in rows if row[0] not in removed]
        output.sort(key=lambda row: row[2])
        args.file.write_text("\n".join([title, *("\t".join(row) for row in output)]) + "\n", encoding="utf-8", newline="\n")
    print({key: value for key, value in report.items() if key != "matches"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
