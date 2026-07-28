#!/usr/bin/env python3
"""Download indexed PDF/PostScript links and extract defensible document dates."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from dateutil import parser as date_parser


USER_AGENT = "io-links-document-date-audit/1.0"
DOCUMENT_RE = re.compile(r"\.(?:pdf|ps|ps\.gz)(?:$|[?#])", re.I)
MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)"
)
DATE_RE = re.compile(
    rf"\b(?:{MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?[,]?\s+\d{{4}}|"
    rf"\d{{1,2}}\s+{MONTH}\s+\d{{4}}|{MONTH}\s+\d{{4}})\b",
    re.I,
)
YEAR_RE = re.compile(r"(?<!\d)(18\d{2}|19\d{2}|20\d{2})(?!\d)")
PUBLICATION_HINT_RE = re.compile(
    r"\b(?:published|publication|proceedings|conference|journal|volume|"
    r"technical report|copyright|©|appeared in|to appear)\b",
    re.I,
)
CREATION_HINT_RE = re.compile(
    r"\b(?:submitted|submission|thesis|dissertation|dated|version|revised)\b",
    re.I,
)


def normalize(raw: str) -> str | None:
    raw = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", raw, flags=re.I).strip(" ,.;")
    try:
        parsed = date_parser.parse(raw, fuzzy=False, default=datetime(1, 1, 1))
    except (OverflowError, ValueError):
        match = YEAR_RE.search(raw)
        return match.group(1) if match else None
    if parsed.year < 1800 or parsed.date() > date.today():
        return None
    has_month = bool(re.search(MONTH, raw, re.I))
    has_day = bool(re.search(r"\b\d{1,2}\b", raw))
    if has_month and has_day:
        return parsed.date().isoformat()
    if has_month:
        return f"{parsed.year:04d}-{parsed.month:02d}"
    return f"{parsed.year:04d}"


def run_text(command: list[str], timeout: int = 60) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return result.stdout


def metadata_date(path: Path, pdfinfo: Path) -> tuple[str, str] | None:
    output = run_text([str(pdfinfo), str(path)], timeout=30)
    for key in ("CreationDate", "ModDate"):
        match = re.search(rf"^{key}:\s*(.+)$", output, re.M)
        if not match:
            continue
        value = normalize(match.group(1))
        if value:
            status = "created" if key == "CreationDate" else "modified"
            return status, value
    return None


def page_evidence(text: str) -> tuple[str, str, str] | None:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line][:180]
    for line in lines:
        date_match = DATE_RE.search(line)
        if date_match and PUBLICATION_HINT_RE.search(line):
            value = normalize(date_match.group(0))
            if value:
                return "publication", value, line[:300]
        if date_match and CREATION_HINT_RE.search(line):
            value = normalize(date_match.group(0))
            if value:
                return "created", value, line[:300]
    for index, line in enumerate(lines[:100]):
        date_match = DATE_RE.fullmatch(line.strip(" ,.;"))
        if not date_match:
            continue
        nearby = " ".join(lines[max(0, index - 8) : index + 3])
        if CREATION_HINT_RE.search(nearby):
            value = normalize(date_match.group(0))
            if value:
                return "created", value, nearby[:300]
    for line in lines[:120]:
        if not (PUBLICATION_HINT_RE.search(line) or CREATION_HINT_RE.search(line)):
            continue
        years = [int(value) for value in YEAR_RE.findall(line)]
        years = [value for value in years if 1800 <= value <= date.today().year]
        if years:
            status = "publication" if PUBLICATION_HINT_RE.search(line) else "created"
            return status, str(min(years)), line[:300]
    return None


def download(url: str, destination: Path, timeout: float) -> tuple[int, str]:
    if destination.exists() and destination.stat().st_size > 1_000:
        return destination.stat().st_size, "cache"
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        stream=True,
        allow_redirects=True,
    )
    response.raise_for_status()
    maximum = 50 * 1024 * 1024
    size = 0
    temporary = destination.with_suffix(destination.suffix + ".part")
    with temporary.open("wb") as handle:
        for chunk in response.iter_content(131_072):
            if not chunk:
                continue
            size += len(chunk)
            if size > maximum:
                raise RuntimeError("document exceeds 50 MiB")
            handle.write(chunk)
    if size <= 1_000:
        raise RuntimeError("downloaded document is too small")
    temporary.replace(destination)
    return size, response.headers.get("Content-Type", "")


def inspect(
    url: str, output_dir: Path, pdftotext: Path, pdfinfo: Path, timeout: float
) -> dict:
    suffix = ".ps" if re.search(r"\.ps(?:$|[?#])", urlparse(url).path, re.I) else ".pdf"
    path = output_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:20]}{suffix}"
    result = {"url": url, "path": str(path), "status": None, "date": None}
    try:
        size, content_type = download(url, path, timeout)
        result.update(bytes=size, content_type=content_type)
        text = run_text(
            [str(pdftotext), "-f", "1", "-l", "3", "-layout", str(path), "-"],
            timeout=90,
        )
        evidence = page_evidence(text)
        if evidence:
            status, value, detail = evidence
            result.update(
                status=status,
                date=value,
                source="document-page",
                evidence=detail,
            )
        else:
            metadata = metadata_date(path, pdfinfo)
            if metadata:
                status, value = metadata
                result.update(
                    status=status,
                    date=value,
                    source="document-metadata",
                    evidence=f"PDF {status} metadata",
                )
            else:
                result.update(source="unresolved", evidence="no usable document date")
    except Exception as exc:
        result.update(source="error", evidence=f"{type(exc).__name__}: {exc}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/pdfs/indexed"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/indexed-document-audit.json")
    )
    parser.add_argument("--pdftotext", type=Path, required=True)
    parser.add_argument("--pdfinfo", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument(
        "--current-status",
        action="append",
        default=[],
        help="Current row status to audit; defaults to indexed.",
    )
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument(
        "--include-host",
        action="append",
        default=[],
        help="Limit inspection to this hostname; may be specified more than once.",
    )
    parser.add_argument(
        "--cached-only",
        action="store_true",
        help="Inspect only documents that are already present in the output directory.",
    )
    args = parser.parse_args()
    if not args.current_status:
        args.current_status = ["indexed"]

    urls = []
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if (
            len(parts) == 3
            and parts[1] in set(args.current_status)
            and (not args.date_from or parts[2] >= args.date_from)
            and (not args.date_to or parts[2] <= args.date_to)
            and DOCUMENT_RE.search(urlparse(parts[0]).path)
        ):
            urls.append(parts[0])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.include_host:
        hosts = {host.lower() for host in args.include_host}
        urls = [
            url for url in urls if (urlparse(url).hostname or "").lower() in hosts
        ]
    if args.cached_only:
        urls = [
            url
            for url in urls
            if (
                args.output_dir
                / (
                    f"{hashlib.sha256(url.encode()).hexdigest()[:20]}"
                    + (
                        ".ps"
                        if re.search(
                            r"\.ps(?:$|[?#])", urlparse(url).path, re.I
                        )
                        else ".pdf"
                    )
                )
            ).exists()
            if (
                args.output_dir
                / (
                    f"{hashlib.sha256(url.encode()).hexdigest()[:20]}"
                    + (
                        ".ps"
                        if re.search(
                            r"\.ps(?:$|[?#])", urlparse(url).path, re.I
                        )
                        else ".pdf"
                    )
                )
            ).stat().st_size
            > 1_000
        ]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                inspect,
                url,
                args.output_dir.resolve(),
                args.pdftotext.resolve(),
                args.pdfinfo.resolve(),
                args.timeout,
            ): url
            for url in urls
        }
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            results.append(future.result())
            if count % 25 == 0 or count == len(futures):
                resolved = sum(bool(item.get("date")) for item in results)
                print(f"{count}/{len(futures)} checked; {resolved} dated", flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(sorted(results, key=lambda item: item["url"]), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
