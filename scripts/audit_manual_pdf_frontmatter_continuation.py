#!/usr/bin/env python3
"""Record dates verified from downloaded PDF front matter and exact metadata."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path


INPUT = Path("io_links.md")
OUTPUT = Path("scratch/manual-pdf-frontmatter-continuation-audit.json")
DATE_RE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")

RESULTS = [
    {
        "url": (
            "https://cronfa.swansea.ac.uk/Record/cronfa64152/Download/"
            "64152__30604__9432b09ebca14099a3bb61fc19f22e8a.pdf"
        ),
        "status": "publication",
        "date": "2023-12-15",
        "confidence": "high",
        "evidence": (
            "Rendered first page identifies ICBTA 2023, December 15-17, 2023; "
            "exact-title Crossref record 10.1145/3651655.3651656 gives "
            "published-print 2023-12-15."
        ),
        "source_url": "https://doi.org/10.1145/3651655.3651656",
        "cache_path": "tmp/pdfs/indexed/db3ba24f346e62c7e33d.pdf",
        "render_path": "tmp/pdfs/frontmatter/swansea-01.png",
    },
    {
        "url": (
            "https://iris.uniupo.it/retrieve/"
            "ab1f4432-8581-4ef5-8f13-766d751b317e/proceedings.pdf"
        ),
        "status": "publication",
        "date": "2025-04-22",
        "confidence": "high",
        "evidence": (
            "Rendered first page matches the title and authors of arXiv:2504.15936; "
            "arXiv records its first submission on 2025-04-22. The page's "
            "'CVIT 2016' text is a LIPIcs template placeholder and was rejected."
        ),
        "source_url": "https://arxiv.org/abs/2504.15936",
        "cache_path": "tmp/pdfs/indexed/74423c5298cc9f825560.pdf",
        "render_path": "tmp/pdfs/frontmatter/uniupo-01.png",
    },
    {
        "url": "https://research.chalmers.se/publication/501384/file/501384_Fulltext.pdf",
        "status": "publication",
        "date": "2018-02",
        "confidence": "high",
        "evidence": (
            "Rendered repository cover identifies the original DOI "
            "10.1016/j.jlamp.2017.12.003 and cites the published paper as 2018; "
            "the exact-title Crossref record gives published-print 2018-02."
        ),
        "source_url": "https://doi.org/10.1016/j.jlamp.2017.12.003",
        "cache_path": "tmp/pdfs/indexed/b5c9c818056bac55865a.pdf",
        "render_path": "tmp/pdfs/frontmatter/chalmers-01.png",
    },
    {
        "url": "https://www.monoidal.net/hdr.pdf",
        "status": "created",
        "date": "2024-09-24",
        "confidence": "high",
        "evidence": (
            "Rendered thesis title page states that the HDR was presented and "
            "defended on 24 September 2024; arXiv:2410.13337 independently "
            "identifies the same work and presentation date."
        ),
        "source_url": "https://arxiv.org/abs/2410.13337",
        "cache_path": "tmp/pdfs/indexed/8f10c7b9f231cdc3a9cf.pdf",
        "render_path": "tmp/pdfs/frontmatter/monoidal-001.png",
    },
]


def main() -> None:
    indexed: dict[str, str] = {}
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) == 3 and fields[1] == "indexed":
            indexed[fields[0]] = fields[2]

    for item in RESULTS:
        assert item["url"] in indexed, f"not currently indexed: {item['url']}"
        assert DATE_RE.fullmatch(item["date"])
        normalized = item["date"] + "-01" * (3 - len(item["date"].split("-")))
        assert date.fromisoformat(normalized) <= date.today()
        item["old_date"] = indexed[item["url"]]
        assert Path(item["cache_path"]).exists()
        assert Path(item["render_path"]).exists()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "summary": {
                    "targets": len(RESULTS),
                    "resolved": len(RESULTS),
                    "unresolved": 0,
                },
                "results": RESULTS,
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({"resolved": len(RESULTS), "output": str(OUTPUT)})


if __name__ == "__main__":
    main()
