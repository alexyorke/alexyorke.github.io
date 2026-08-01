#!/usr/bin/env python3
"""Fingerprint the full local URL archive and report/apply substantive duplicates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from audit_document_content_duplicates import metadata_rank, url_rank


WORDS = re.compile(r"[a-z0-9]+")
MIN_WORDS = 100
MIN_SAMPLE = 20
FINGERPRINT_VERSION = 3
BLOCK_TEXT = (
    "cloudflare ray id", "just a moment", "verify you are human",
    "checking your browser", "enable javascript and cookies to continue",
    "access denied", "request blocked", "too many requests",
)
ERROR_TEXT = (
    "404 page not found", "404 not found", "page not found",
    "the requested url was not found", "the requested page could not be found",
    "this page does not exist", "we couldn t find the page",
)


class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "template"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def extract_text(path: Path, content_type: str) -> str | None:
    media_type = content_type.split(";", 1)[0].casefold()
    prefix = path.read_bytes()[:8]
    if media_type == "application/pdf" or prefix.startswith(b"%PDF"):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "text.txt"
            result = subprocess.run(
                ["pdftotext", "-enc", "UTF-8", str(path), str(output)],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not output.exists():
                return None
            return output.read_text(encoding="utf-8", errors="ignore")
    if "html" in media_type or path.suffix.casefold() in {".html", ".htm"}:
        parser = VisibleText()
        parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
        return " ".join(parser.parts)
    if media_type.startswith("text/") or path.suffix.casefold() in {".txt", ".md", ".tex"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    return None


def simhash(tokens: list[str]) -> str:
    counts = Counter(tokens)
    vector = [0] * 64
    for token, weight in counts.items():
        value = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
        for bit in range(64):
            vector[bit] += weight if value & (1 << bit) else -weight
    result = sum(1 << bit for bit, value in enumerate(vector) if value >= 0)
    return f"{result:016x}"


def fingerprint(item: dict[str, object], archive: Path) -> dict[str, object]:
    relative = item.get("file")
    if not isinstance(relative, str):
        return {"error": "no_file"}
    path = archive / relative
    if not path.exists():
        return {"error": "missing_file"}
    try:
        text = extract_text(path, str(item.get("content_type", "")))
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        return {"error": type(exc).__name__}
    if text is None:
        return {"error": "unsupported_type"}
    tokens = WORDS.findall(text.casefold())
    joined_prefix = " ".join(tokens[:500])
    if len(tokens) < MIN_WORDS:
        return {"error": "too_little_text", "words": len(tokens)}
    if any(pattern in joined_prefix for pattern in BLOCK_TEXT):
        return {"error": "blocked_text", "words": len(tokens)}
    if any(pattern in joined_prefix for pattern in ERROR_TEXT):
        return {"error": "soft_error_text", "words": len(tokens)}
    sample: set[str] = set()
    for index in range(len(tokens) - 4):
        shingle = " ".join(tokens[index : index + 5]).encode()
        digest = hashlib.blake2b(shingle, digest_size=8).digest()
        if digest[0] < 16:
            sample.add(digest.hex())
    return {
        "version": FINGERPRINT_VERSION,
        "source_sha256": item.get("sha256"),
        "words": len(tokens),
        "sample": sorted(sample),
        "simhash": simhash(tokens),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument("--archive", type=Path, default=Path("tmp/io-links-full-download"))
    parser.add_argument("--cache", type=Path, default=Path("tmp/io-links-full-download/fingerprints.json"))
    parser.add_argument("--report", type=Path, default=Path("tmp/io-links-full-download/duplicate-report.json"))
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    http = json.loads((args.archive / "manifest-latest.json").read_text(encoding="utf-8"))
    browser_path = args.archive / "browser-manifest-latest.json"
    browser = json.loads(browser_path.read_text(encoding="utf-8")) if browser_path.exists() else {}
    effective = {url: item for url, item in http.items() if item.get("state") == "ok"}
    effective.update({url: item for url, item in browser.items() if item.get("state") == "ok"})
    final_targets: dict[str, list[str]] = defaultdict(list)
    for url, item in effective.items():
        final = str(item.get("final_url", url)).rstrip("/")
        final_targets[final].append(url)
    shared_redirects = {
        url
        for final, urls in final_targets.items()
        if len(urls) > 1
        for url in urls
        if url.rstrip("/") != final
    }
    generic_redirects = set()
    for url, item in effective.items():
        original = urlsplit(url)
        final = urlsplit(str(item.get("final_url", url)))
        final_path = final.path.rstrip("/").casefold()
        if (
            original.path.rstrip("/")
            and (original.hostname or "").casefold() != (final.hostname or "").casefold()
            and final_path in {"", "/home", "/research", "/en-us/research"}
        ):
            generic_redirects.add(url)
    effective = {
        url: item for url, item in effective.items()
        if url not in generic_redirects and url not in shared_redirects
    }

    cache = json.loads(args.cache.read_text(encoding="utf-8")) if args.cache.exists() else {}
    pending = [
        url for url, item in effective.items()
        if cache.get(url, {}).get("source_sha256") != item.get("sha256")
        or cache.get(url, {}).get("version") != FINGERPRINT_VERSION
    ]
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fingerprint, effective[url], args.archive): url for url in pending}
        for future in as_completed(futures):
            url = futures[future]
            result = future.result()
            result.setdefault("version", FINGERPRINT_VERSION)
            result.setdefault("source_sha256", effective[url].get("sha256"))
            cache[url] = result
            completed += 1
            if completed % 100 == 0:
                args.cache.write_text(json.dumps(cache, sort_keys=True) + "\n", encoding="utf-8")
                print({"fingerprinted_now": completed, "remaining": len(pending) - completed}, flush=True)
    args.cache.write_text(json.dumps(cache, sort_keys=True) + "\n", encoding="utf-8")

    usable = {
        url: item for url, item in cache.items()
        if url in effective and len(item.get("sample", [])) >= MIN_SAMPLE and item.get("simhash")
    }
    pairs: set[tuple[str, str]] = set()
    exact: dict[str, list[str]] = defaultdict(list)
    postings: dict[str, list[str]] = defaultdict(list)
    bands: dict[tuple[int, str], list[str]] = defaultdict(list)
    for url, item in usable.items():
        exact[str(item.get("source_sha256"))].append(url)
        for shingle in item["sample"]:
            postings[shingle].append(url)
        value = item["simhash"]
        for band in range(4):
            bands[(band, value[band * 4 : band * 4 + 4])].append(url)
    for group in exact.values():
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                pairs.add(tuple(sorted((left, right))))
    shared: dict[tuple[str, str], int] = defaultdict(int)
    for group in postings.values():
        if 1 < len(group) <= 50:
            for index, left in enumerate(group):
                for right in group[index + 1 :]:
                    shared[tuple(sorted((left, right)))] += 1
    pairs.update(pair for pair, count in shared.items() if count >= 8)
    for group in bands.values():
        if 1 < len(group) <= 50:
            for index, left in enumerate(group):
                for right in group[index + 1 :]:
                    pairs.add(tuple(sorted((left, right))))

    matches = []
    parent = {url: url for url in usable}
    def find(url: str) -> str:
        while parent[url] != url:
            parent[url] = parent[parent[url]]
            url = parent[url]
        return url
    def union(left: str, right: str) -> None:
        parent[find(right)] = find(left)
    for left, right in sorted(pairs):
        a = set(usable[left]["sample"])
        b = set(usable[right]["sample"])
        overlap = len(a & b)
        jaccard = overlap / len(a | b)
        left_hash = int(usable[left]["simhash"], 16)
        right_hash = int(usable[right]["simhash"], 16)
        simhash_similarity = 1 - (left_hash ^ right_hash).bit_count() / 64
        exact_bytes = usable[left].get("source_sha256") == usable[right].get("source_sha256")
        if exact_bytes or (jaccard >= args.threshold and simhash_similarity >= 0.9):
            union(left, right)
            matches.append({
                "left": left, "right": right, "exact_bytes": exact_bytes,
                "jaccard": jaccard, "simhash_similarity": simhash_similarity,
            })

    lines = args.file.read_text(encoding="utf-8").splitlines()
    rows = [line.split("\t") for line in lines[1:] if len(line.split("\t")) == 3]
    row_by_url = {row[0]: row for row in rows}
    components: dict[str, list[list[str]]] = defaultdict(list)
    for url in usable:
        if url in row_by_url:
            components[find(url)].append(row_by_url[url])
    groups = [group for group in components.values() if len(group) > 1]
    removed: dict[str, str] = {}
    replacements: dict[str, list[str]] = {}
    report_groups = []
    for group in groups:
        winner_row = max(group, key=lambda row: (metadata_rank(row), url_rank(row)))
        replacement = winner_row
        replacements[winner_row[0]] = replacement
        losers = [row for row in group if row[0] != winner_row[0]]
        for row in losers:
            removed[row[0]] = winner_row[0]
        report_groups.append({"kept": replacement, "removed": losers})

    report = {
        "effective_ok_responses": len(effective), "excluded_generic_redirects": len(generic_redirects),
        "excluded_shared_redirects": len(shared_redirects),
        "fingerprinted_now": len(pending),
        "usable_text_fingerprints": len(usable), "candidate_pairs": len(pairs),
        "matching_pairs": len(matches), "duplicate_groups": len(groups),
        "removed_records": len(removed), "groups": report_groups, "matches": matches,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.apply and removed:
        output = [replacements.get(row[0], row) for row in rows if row[0] not in removed]
        output.sort(key=lambda row: row[2])
        args.file.write_text("\n".join([lines[0], *("\t".join(row) for row in output)]) + "\n", encoding="utf-8", newline="\n")
    print({key: value for key, value in report.items() if key not in {"groups", "matches"}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
