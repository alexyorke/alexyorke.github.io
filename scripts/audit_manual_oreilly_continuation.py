#!/usr/bin/env python3
"""Record exact-edition dates verified on O'Reilly and publisher pages."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path


INPUT = Path("io_links.md")
OUTPUT = Path("scratch/manual-oreilly-continuation-audit.json")
DATE_RE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")

BOOKS = {
    "9781484244807": {
        "date": "2019-04",
        "source_url": (
            "https://www.oreilly.com/library/view/practical-haskell-a/"
            "9781484244807/"
        ),
        "evidence": (
            "O'Reilly exact-edition page identifies ISBN 9781484244807 and "
            "publication month April 2019."
        ),
    },
    "9781680502756": {
        "date": "2017-07-21",
        "source_url": "https://partners.pragprog.com/catalog/506",
        "evidence": (
            "PragProg's official partner catalog identifies Safari ISBN "
            "9781680502756 and Published 2017-07-21."
        ),
    },
    "9781492077886": {
        "date": "2021-05",
        "source_url": (
            "https://www.oreilly.com/library/view/programming-scala-3rd/"
            "9781492077886/"
        ),
        "evidence": (
            "O'Reilly exact-edition page identifies ISBN 9781492077886 and "
            "publication month May 2021."
        ),
    },
    "9798868812828": {
        "date": "2025-04",
        "source_url": (
            "https://www.oreilly.com/library/view/magical-haskell-a/"
            "9798868812828/"
        ),
        "evidence": (
            "O'Reilly exact-edition page identifies ISBN 9798868812828 and "
            "publication month April 2025."
        ),
    },
    "9781449326036": {
        "date": "2012-10",
        "source_url": (
            "https://www.oreilly.com/library/view/programming-f-3-0/"
            "9781449326036/"
        ),
        "evidence": (
            "O'Reilly exact-edition page identifies ISBN 9781449326036 and "
            "publication month October 2012."
        ),
    },
    "9781484245071": {
        "date": "2019-06",
        "source_url": (
            "https://www.oreilly.com/library/view/haskell-quick-syntax/"
            "9781484245071/"
        ),
        "evidence": (
            "O'Reilly exact-edition page identifies ISBN 9781484245071 and "
            "publication month June 2019."
        ),
    },
    "9781788477840": {
        "date": "2017-08-31",
        "source_url": (
            "https://www.packtpub.com/en-id/product/"
            "learning-functional-programming-with-f-9781788477840"
        ),
        "evidence": (
            "Packt's exact-ISBN product page explicitly gives publication "
            "date 2017-08-31 for ISBN 9781788477840."
        ),
    },
}


def main() -> None:
    indexed: dict[str, str] = {}
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) == 3 and fields[1] == "indexed":
            indexed[fields[0]] = fields[2]

    results: list[dict[str, str]] = []
    for url, old_date in indexed.items():
        if "www.oreilly.com/" not in url:
            continue
        match = re.search(r"/(\d{13})(?:/|$)", url)
        if not match or match.group(1) not in BOOKS:
            continue
        metadata = BOOKS[match.group(1)]
        value = metadata["date"]
        assert DATE_RE.fullmatch(value)
        normalized = value + "-01" * (3 - len(value.split("-")))
        assert date.fromisoformat(normalized) <= date.today()
        results.append(
            {
                "url": url,
                "old_date": old_date,
                "status": "publication",
                "date": value,
                "confidence": "high",
                "evidence": metadata["evidence"],
                "source_url": metadata["source_url"],
            }
        )

    matched_isbns = {
        re.search(r"/(\d{13})(?:/|$)", item["url"]).group(1) for item in results
    }
    assert matched_isbns == set(BOOKS), (
        f"expected ISBNs {sorted(BOOKS)}, got {sorted(matched_isbns)}"
    )
    assert len(results) == 8, f"expected 8 current URL variants, got {len(results)}"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "summary": {
                    "targets": len(results),
                    "resolved": len(results),
                    "unresolved": 0,
                },
                "results": results,
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({"resolved": len(results), "output": str(OUTPUT)})


if __name__ == "__main__":
    main()
