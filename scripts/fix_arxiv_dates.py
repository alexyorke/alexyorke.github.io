#!/usr/bin/env python3
"""Audit arXiv dates from downloaded PDFs and update io_links.md."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests


ARXIV_HOSTS = {"arxiv.org", "export.arxiv.org"}
STAMP_RE = re.compile(
    r"arXiv:\S+.*?\b("
    r"\d{1,2}\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[a-z]*\s+\d{4})\b",
    re.I,
)
DATE_FORMATS = ("%d %b %Y", "%d %B %Y")


def arxiv_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in ARXIV_HOSTS:
        return None
    path = parsed.path
    for prefix in ("/abs/", "/pdf/", "/html/"):
        if path.startswith(prefix):
            value = path[len(prefix) :].removesuffix(".pdf").strip("/")
            return value or None
    return None


def encoded_month(identifier: str) -> str | None:
    base = re.sub(r"v\d+$", "", identifier)
    modern = re.match(r"^(\d{2})(\d{2})\.\d+$", base)
    old = re.match(r"^[a-z-]+/(\d{2})(\d{2})\d+$", base, re.I)
    match = modern or old
    if not match:
        return None
    year = 2000 + int(match.group(1))
    month = int(match.group(2))
    if not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}"


def parse_stamp(text: str) -> tuple[str, str] | None:
    normalized = " ".join(text.split())
    match = STAMP_RE.search(normalized)
    if not match:
        return None
    raw = match.group(1)
    for fmt in DATE_FORMATS:
        try:
            date = datetime.strptime(raw, fmt).date().isoformat()
            return date, match.group(0)[:240]
        except ValueError:
            continue
    return None


def parse_pdf_creation(pdf: Path, pdfinfo: Path) -> str | None:
    result = subprocess.run(
        [str(pdfinfo), str(pdf)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    for line in result.stdout.splitlines():
        if not line.startswith("CreationDate:"):
            continue
        raw = line.split(":", 1)[1].strip()
        raw = re.sub(
            r"\s+(?:Pacific|Eastern|Central|Mountain|Greenwich)\s+Standard\s+Time$",
            "",
            raw,
            flags=re.I,
        )
        try:
            return datetime.strptime(raw, "%a %b %d %H:%M:%S %Y").date().isoformat()
        except ValueError:
            return None
    return None


def first_page_text(pdf: Path, pdftotext: Path) -> str:
    result = subprocess.run(
        [str(pdftotext), "-f", "1", "-l", "1", "-layout", str(pdf), "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    return result.stdout


def download_pdf(identifier: str, destination: Path, timeout: float) -> None:
    if destination.exists() and destination.stat().st_size > 1_000:
        return
    url = f"https://arxiv.org/pdf/{identifier}"
    headers = {"User-Agent": "io-links-arxiv-date-audit/1.0"}
    for attempt in range(5):
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        if response.status_code == 200:
            temp = destination.with_suffix(".tmp")
            with temp.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=131_072):
                    if chunk:
                        handle.write(chunk)
            if temp.stat().st_size <= 1_000:
                temp.unlink(missing_ok=True)
                raise RuntimeError(f"Downloaded PDF is too small: {url}")
            temp.replace(destination)
            return
        if response.status_code in {429, 500, 502, 503, 504}:
            time.sleep(2**attempt)
            continue
        raise RuntimeError(f"HTTP {response.status_code}: {url}")
    raise RuntimeError(f"Retries exhausted: {url}")


def inspect_one(
    identifier: str,
    download_dir: Path,
    pdftotext: Path,
    pdfinfo: Path,
    timeout: float,
) -> dict[str, str | int | None]:
    filename = identifier.replace("/", "__") + ".pdf"
    pdf = download_dir / filename
    try:
        download_pdf(identifier, pdf, timeout)
        text = first_page_text(pdf, pdftotext)
        stamp = parse_stamp(text)
        creation = parse_pdf_creation(pdf, pdfinfo)
        encoded = encoded_month(identifier)
        if stamp:
            date, evidence = stamp
            source = "pdf-arxiv-stamp"
        elif creation and (not encoded or creation.startswith(encoded)):
            date = creation
            evidence = f"PDF CreationDate {creation}"
            source = "pdf-creation"
        else:
            date = encoded
            evidence = f"decoded arXiv identifier {identifier}"
            source = "arxiv-id-month"
        return {
            "id": identifier,
            "date": date,
            "source": source,
            "evidence": evidence,
            "pdf_creation": creation,
            "encoded_month": encoded,
            "bytes": pdf.stat().st_size,
            "error": None,
        }
    except Exception as exc:
        return {
            "id": identifier,
            "date": encoded_month(identifier),
            "source": "arxiv-id-month",
            "evidence": f"download/parse failed: {type(exc).__name__}",
            "pdf_creation": None,
            "encoded_month": encoded_month(identifier),
            "bytes": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def load_rows(path: Path) -> tuple[list[str], dict[str, list[int]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    identifiers: dict[str, list[int]] = {}
    for index, line in enumerate(lines):
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        identifier = arxiv_id(parts[0])
        if identifier:
            identifiers.setdefault(identifier, []).append(index)
    return lines, identifiers


def load_report(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {
        item["id"]: item
        for item in json.loads(path.read_text(encoding="utf-8"))
        if item.get("id")
    }


def save_report(path: Path, report: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [report[key] for key in sorted(report)]
    path.write_text(
        json.dumps(ordered, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def apply_report(path: Path, lines: list[str], identifiers: dict[str, list[int]], report: dict[str, dict]) -> int:
    changed = 0
    for identifier, indexes in identifiers.items():
        item = report.get(identifier)
        if not item or not item.get("date"):
            continue
        version = re.search(r"v(\d+)\b", item.get("evidence", ""))
        status = (
            "updated"
            if item.get("source") == "pdf-arxiv-stamp"
            and version
            and int(version.group(1)) > 1
            else "created"
        )
        for index in indexes:
            parts = lines[index].split("\t")
            replacement = f"{parts[0]}\t{status}\t{item['date']}"
            if replacement != lines[index]:
                lines[index] = replacement
                changed += 1
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument("--download-dir", type=Path, default=Path("tmp/pdfs/arxiv"))
    parser.add_argument("--report", type=Path, default=Path("scratch/arxiv-date-evidence.json"))
    parser.add_argument("--pdftotext", type=Path, required=True)
    parser.add_argument("--pdfinfo", type=Path, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    file_path = args.file.resolve()
    lines, identifiers = load_rows(file_path)
    ids = sorted(identifiers)
    selected = ids[args.offset :]
    if args.limit is not None:
        selected = selected[: args.limit]
    args.download_dir.mkdir(parents=True, exist_ok=True)
    report = load_report(args.report)
    print(f"Inspecting {len(selected)} of {len(ids)} unique arXiv identifiers", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                inspect_one,
                identifier,
                args.download_dir.resolve(),
                args.pdftotext.resolve(),
                args.pdfinfo.resolve(),
                args.timeout,
            ): identifier
            for identifier in selected
        }
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            item = future.result()
            report[item["id"]] = item
            if count % 25 == 0 or count == len(futures):
                stamps = sum(x.get("source") == "pdf-arxiv-stamp" for x in report.values())
                errors = sum(bool(x.get("error")) for x in report.values())
                print(f"{count}/{len(futures)} complete; stamps={stamps}; errors={errors}", flush=True)
    save_report(args.report, report)
    if args.apply:
        changed = apply_report(file_path, lines, identifiers, report)
        print(f"Updated {changed} arXiv URL rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
