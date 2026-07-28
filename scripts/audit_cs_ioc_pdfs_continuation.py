#!/usr/bin/env python3
"""Download, extract, and render current indexed cs.ioc.ee PDFs."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from pypdf import PdfReader
from urllib.request import Request, urlopen


INPUT = Path("io_links.md")
PDF_DIR = Path("tmp/pdfs/cs_ioc")
REPORT = Path("scratch/cs-ioc-pdf-frontmatter.json")
PDFTOPPM = Path(
    r"C:\Users\yorke\.cache\codex-runtimes\codex-primary-runtime"
    r"\dependencies\native\poppler\Library\bin\pdftoppm.exe"
)


def safe_name(index: int, url: str) -> str:
    leaf = Path(urlparse(url).path).name
    leaf = re.sub(r"[^A-Za-z0-9_.-]+", "-", leaf)
    return f"{index:02d}-{leaf}"


def main() -> None:
    urls = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        url = fields[0]
        if urlparse(url).hostname == "cs.ioc.ee" and urlparse(url).path.endswith(
            ".pdf"
        ):
            urls.append(url)

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for index, url in enumerate(urls, 1):
        pdf_path = PDF_DIR / safe_name(index, url)
        if not pdf_path.exists():
            request = Request(url, headers={"User-Agent": "io-links-date-audit/1.0"})
            with urlopen(request, timeout=60) as response:
                pdf_path.write_bytes(response.read())

        reader = PdfReader(pdf_path)
        text = "\n".join(
            (page.extract_text() or "") for page in reader.pages[:3]
        )
        prefix = pdf_path.with_suffix("")
        subprocess.run(
            [
                str(PDFTOPPM),
                "-f",
                "1",
                "-singlefile",
                "-png",
                "-r",
                "110",
                str(pdf_path),
                str(prefix),
            ],
            check=True,
            timeout=60,
        )
        records.append(
            {
                "url": url,
                "pdf": str(pdf_path),
                "png": str(prefix.with_suffix(".png")),
                "pages": len(reader.pages),
                "metadata": {
                    str(key): str(value)
                    for key, value in (reader.metadata or {}).items()
                },
                "first_three_pages_text": text,
            }
        )
        print(f"{index}/{len(urls)} {pdf_path.name}", flush=True)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps({"records": records}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
