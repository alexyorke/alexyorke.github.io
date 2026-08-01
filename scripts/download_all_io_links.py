#!/usr/bin/env python3
"""Resumably archive every URL in io_links.md with block-page classification."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests


MAX_BYTES = 80 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)
BLOCK_PATTERNS = (
    b"cf-chl-",
    b"cloudflare ray id",
    b"just a moment...",
    b"attention required! | cloudflare",
    b"verify you are human",
    b"checking your browser",
    b"enable javascript and cookies to continue",
    b"captcha",
    b"access denied |",
    b"request blocked",
    b"too many requests",
)
EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/postscript": ".ps",
    "application/zip": ".zip",
    "application/gzip": ".gz",
    "application/json": ".json",
    "application/xml": ".xml",
    "text/html": ".html",
    "text/plain": ".txt",
}
_local = threading.local()


def session() -> requests.Session:
    if not hasattr(_local, "session"):
        value = requests.Session()
        value.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "application/pdf;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        _local.session = value
    return _local.session


def safe_name(url: str, content_type: str) -> str:
    parsed = urlsplit(url)
    leaf = unquote(parsed.path.rstrip("/").rsplit("/", 1)[-1]) or "index"
    leaf = re.sub(r"[^A-Za-z0-9._-]+", "_", leaf).strip("._")[:80] or "index"
    suffix = Path(leaf).suffix.lower()
    media_type = content_type.split(";", 1)[0].strip().lower()
    if not suffix or len(suffix) > 8:
        suffix = EXTENSIONS.get(media_type) or mimetypes.guess_extension(media_type) or ".bin"
        leaf = f"{leaf}{suffix}"
    return f"{hashlib.sha256(url.encode()).hexdigest()[:20]}_{leaf}"


def classify(status: int, content_type: str, prefix: bytes, size: int) -> tuple[str, str]:
    lowered = prefix.lower()
    if status in (401, 403, 407, 409, 423, 429, 451, 503):
        return "blocked", f"http_{status}"
    if status < 200 or status >= 400:
        return "error", f"http_{status}"
    if any(pattern in lowered for pattern in BLOCK_PATTERNS):
        return "blocked", "challenge_content"
    if size < 128:
        return "error", "tiny_response"
    if "text/html" in content_type.lower() and b"<html" not in lowered and b"<!doctype" not in lowered:
        return "error", "invalid_html"
    return "ok", ""


def download(url: str, content_dir: Path) -> dict[str, object]:
    try:
        with session().get(url, stream=True, timeout=(8, 25), allow_redirects=True) as response:
            content_type = response.headers.get("content-type", "")
            filename = safe_name(url, content_type)
            path = content_dir / filename
            size = 0
            prefix = b""
            digest = hashlib.sha256()
            with path.open("wb") as handle:
                for chunk in response.iter_content(128 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > MAX_BYTES:
                        handle.close()
                        path.unlink(missing_ok=True)
                        return {"url": url, "state": "error", "reason": "too_large"}
                    if len(prefix) < 128 * 1024:
                        prefix += chunk[: 128 * 1024 - len(prefix)]
                    digest.update(chunk)
                    handle.write(chunk)
            state, reason = classify(response.status_code, content_type, prefix, size)
            return {
                "url": url,
                "state": state,
                "reason": reason,
                "status": response.status_code,
                "content_type": content_type,
                "size": size,
                "sha256": digest.hexdigest(),
                "file": f"content/{filename}",
                "final_url": response.url,
                "method": "http",
            }
    except requests.RequestException as exc:
        return {"url": url, "state": "error", "reason": type(exc).__name__, "method": "http"}
    except OSError as exc:
        return {"url": url, "state": "error", "reason": type(exc).__name__, "method": "http"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument("--output", type=Path, default=Path("tmp/io-links-full-download"))
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    content_dir = args.output / "content"
    content_dir.mkdir(exist_ok=True)
    manifest = args.output / "manifest.jsonl"
    existing: dict[str, dict[str, object]] = {}
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                existing[item["url"]] = item
            except (json.JSONDecodeError, KeyError):
                continue

    urls = []
    for line in args.file.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 3:
            urls.append(parts[0])
    pending = [
        url for url in urls
        if url not in existing or (args.retry_errors and existing[url].get("state") != "ok")
    ]
    with manifest.open("a", encoding="utf-8", newline="\n") as output:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(download, url, content_dir): url for url in pending}
            for count, future in enumerate(as_completed(futures), 1):
                item = future.result()
                output.write(json.dumps(item, ensure_ascii=True) + "\n")
                output.flush()
                existing[item["url"]] = item
                if count % 250 == 0:
                    states: dict[str, int] = {}
                    for value in existing.values():
                        state = str(value.get("state"))
                        states[state] = states.get(state, 0) + 1
                    print({"completed_now": count, "remaining": len(pending) - count, **states}, flush=True)

    latest = args.output / "manifest-latest.json"
    latest.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    states: dict[str, int] = {}
    for item in existing.values():
        state = str(item.get("state"))
        states[state] = states.get(state, 0) + 1
    print({"total": len(urls), "downloaded_now": len(pending), **states})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
