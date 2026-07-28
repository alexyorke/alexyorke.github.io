#!/usr/bin/env python3
"""Audit indexed scholarly-host links for defensible publication dates.

The script deliberately limits itself to the host set requested for this
continuation.  Raw HTTP responses are cached so repeated analysis does not
refetch the same publisher or repository record.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "io_links.md"
OUTPUT = ROOT / "scratch" / "scholarly-hosts-continuation-audit.json"
CACHE = ROOT / "tmp" / "audit-scholarly-hosts"

HOSTS = {
    "dl.acm.org",
    "www.cambridge.org",
    "academic.oup.com",
    "repository.ubn.ru.nl",
    "www.research.ed.ac.uk",
    "www.diva-portal.org",
    "repository.upenn.edu",
}

DATE_RE = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
DOI_RE = re.compile(r"/doi/(?:abs/|pdf/|full/|book/|proceedings/)?(10\.\d{4,9}/[^?#]+)")

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "io-links-date-audit/1.0 "
            "(mailto:alexyorke@users.noreply.github.com)"
        )
    }
)

MANUAL: dict[str, dict[str, str]] = {}


def manual_add(
    urls: list[str],
    date: str,
    evidence: str,
    source_url: str,
    *,
    status: str = "publication",
    confidence: str = "high",
) -> None:
    for url in urls:
        MANUAL[url] = {
            "status": status,
            "source_type": status,
            "date": date,
            "confidence": confidence,
            "evidence": evidence,
            "source_url": source_url,
        }


# Official Oxford Academic pages and exact DOI metadata.
manual_add(
    [
        "https://academic.oup.com/comjnl/article-pdf/32/2/162/1445725/320162.pdf",
        "https://academic.oup.com/comjnl/article-abstract/32/2/162/543564",
    ],
    "1989-01-01",
    "The official Oxford Academic record for 'Functional Programming and Operating Systems' explicitly says Published 01 January 1989.",
    "https://academic.oup.com/comjnl/article-abstract/32/2/162/543564",
)
manual_add(
    [
        "https://academic.oup.com/jos/advance-article-pdf/doi/10.1093/jos/ffad012/65044641/ffad012.pdf",
        "https://academic.oup.com/jos/article/42/4/353/8307116",
    ],
    "2025-10-31",
    "The official Oxford Academic record for 'Static and dynamic exceptional scope' (DOI 10.1093/jos/ffad012) says Published 31 October 2025.",
    "https://academic.oup.com/jos/advance-article/doi/10.1093/jos/ffad012/8307116",
)
manual_add(
    ["https://academic.oup.com/comjnl/article-pdf/31/3/243/1157325/310243.pdf"],
    "1988-01-01",
    "The official Oxford Academic record for 'Nondeterminism with Referential Transparency in Functional Programming Languages' explicitly says Published 01 January 1988.",
    "https://academic.oup.com/comjnl/article-abstract/31/3/243/417117",
)
manual_add(
    [
        "https://academic.oup.com/nsr/article/2/3/349/1427872?login=false",
        "https://academic.oup.com/nsr/article/2/3/349/1427872",
    ],
    "2015-07-13",
    "Exact DOI metadata for 'How functional programming mattered' (10.1093/nsr/nwv042) gives the online publication date as 13 July 2015; this is more precise than the September 2015 issue date.",
    "https://api.crossref.org/works/10.1093/nsr/nwv042",
)
manual_add(
    [
        "https://academic.oup.com/comjnl/article-pdf/33/5/460/1299545/330460.pdf",
        "https://academic.oup.com/comjnl/article-abstract/33/5/460/480501",
    ],
    "1990-05-01",
    "Exact DOI metadata for 'Continuations Implement Generators and Streams' (10.1093/comjnl/33.5.460) gives the print publication date as 01 May 1990.",
    "https://api.crossref.org/works/10.1093/comjnl/33.5.460",
)
manual_add(
    [
        "https://academic.oup.com/comjnl/article/40/9/572/343036",
        "https://academic.oup.com/comjnl/article-abstract/40/9/572/343036",
    ],
    "1997-09-01",
    "Exact DOI metadata for 'Lazy Functional Programs in a Concurrent Environment' (10.1093/comjnl/40.9.572) gives the print publication date as 01 September 1997.",
    "https://api.crossref.org/works/10.1093/comjnl/40.9.572",
)
manual_add(
    ["https://academic.oup.com/book/5354/chapter/148148869"],
    "2005-10-06",
    "The official Oxford Academic chapter record for 'Interactive Programs and Weakly Final Coalgebras in Dependent Type Theory' says Published 06 October 2005.",
    "https://academic.oup.com/book/5354/chapter/148148869",
)
manual_add(
    ["https://academic.oup.com/logcom/article-pdf/14/4/571/2758282/140571.pdf"],
    "2004-08-01",
    "The official Oxford Academic record for 'Monad-independent Dynamic Logic in HasCasl' says Published 01 August 2004.",
    "https://academic.oup.com/logcom/article-abstract/14/4/571/933561",
)
manual_add(
    ["https://academic.oup.com/logcom/article-pdf/29/4/487/28917421/exv078.pdf"],
    "2019-07-08",
    "The official Oxford Academic record for 'Program extraction applied to monadic parsing' says Published 08 July 2019.",
    "https://academic.oup.com/logcom/article-abstract/29/4/487/2917850",
)
manual_add(
    ["https://academic.oup.com/edited-volume/34667/chapter-abstract/295394234"],
    "2015-07-09",
    "The official Oxford Academic record for the chapter 'Monadic Perception' says Published 09 July 2015.",
    "https://academic.oup.com/edited-volume/34667/chapter-abstract/295394234",
)

# Official University of Pennsylvania DSpace dc.date.issued metadata.
for upenn_url, upenn_date, item_id, title in [
    (
        "https://repository.upenn.edu/bitstreams/8d416854-2695-4074-93c6-30ff5fdc91b2/download",
        "2018",
        "0830dcba-46b5-4e89-a7a1-4cd827ca1a2f",
        "Linear/non-Linear Types For Embedded Domain-Specific Languages",
    ),
    (
        "https://repository.upenn.edu/bitstreams/69072158-fade-4334-be54-182522b57de5/download",
        "2018",
        "e5710d2a-99c2-410f-931c-90e9ab7f3663",
        "Formally Verified Quantum Programming",
    ),
    (
        "https://repository.upenn.edu/bitstreams/9eaac6e3-ba5a-4f8e-b2c9-9c68c28881aa/download",
        "2022",
        "7351d241-4818-4a56-a2a5-9f6307849900",
        "Executable Denotational Semantics With Interaction Trees",
    ),
    (
        "https://repository.upenn.edu/bitstreams/ba4b7c2e-5689-4609-8ffe-767634d418db/download",
        "2022",
        "c6f768d5-1589-4b14-8128-94b92b77260a",
        'Mechanized Reasoning About "how" Using Functional Programs And Embeddings',
    ),
    (
        "https://repository.upenn.edu/server/api/core/bitstreams/b705fba2-a929-4f57-924e-ce0b57108d35/content",
        "2016-01-01",
        "e9aae823-5c41-4087-b053-40d0843af53a",
        "Dependent Types In Haskell: Theory And Practice",
    ),
    (
        "https://repository.upenn.edu/bitstreams/7a98446a-9f99-4ee8-b121-3cbef1ee780f/download",
        "2007-06-01",
        "24b5fe79-5a47-447e-948e-b10b6f1e5934",
        "Combining Events And Threads For Scalable Network Services",
    ),
    (
        "https://repository.upenn.edu/bitstreams/f9a54fe3-0396-4d56-9800-15e26d2e1db1/download",
        "2023",
        "b15311ac-56e3-48dd-98e3-f82430bef792",
        "Interaction Trees and Formal Specifications",
    ),
    (
        "https://repository.upenn.edu/bitstreams/9565ea3e-4948-4304-a266-1f4a6fd34762/download",
        "2013-01-01",
        "2dd32265-eae5-4fc9-aabb-3b303502920a",
        "Linear Types, Protocols, and Processes in Classical F°",
    ),
]:
    manual_add(
        [upenn_url],
        upenn_date,
        f"The exact bitstream was traced through the official Penn DSpace bundle API to item {item_id}, whose dc.date.issued is {upenn_date}; title: {title}.",
        f"https://repository.upenn.edu/server/api/core/items/{item_id}",
    )

# Official DiVA repository records.  The records expose only a year for these
# publications, so the audit intentionally does not invent a month or day.
manual_add(
    [
        "https://www.diva-portal.org/smash/get/diva2%3A1004952/FULLTEXT01.pdf",
        "https://www.diva-portal.org/smash/get/diva2:1004952/FULLTEXT01.pdf",
    ],
    "1997",
    "The official DiVA record diva2:1004952 identifies 'Reactive objects in a functional language: an escape from the Evil I' as a conference paper published in 1997.",
    "https://ltu.diva-portal.org/smash/record.jsf?pid=diva2%3A1004952",
)
manual_add(
    ["https://www.diva-portal.org/smash/get/diva2%3A1038657/FULLTEXT01.pdf"],
    "2016",
    "The official DiVA record diva2:1038657 identifies 'A Cross-Platform Scalable I/O Manager for GHC' as a 2016 independent thesis.",
    "https://umu.diva-portal.org/smash/record.jsf?pid=diva2%3A1038657",
)
manual_add(
    [
        "https://www.diva-portal.org/smash/get/diva2%3A142802/FULLTEXT01.pdf",
        "https://www.diva-portal.org/smash/get/diva2:142802/FULLTEXT01.pdf",
    ],
    "2004",
    "The official DiVA record diva2:142802 identifies 'Categorical Unification' as a doctoral thesis published in 2004.",
    "https://umu.diva-portal.org/smash/record.jsf?pid=diva2%3A142802",
)
manual_add(
    ["https://www.diva-portal.org/smash/get/diva2%3A1502080/FULLTEXT01.pdf"],
    "2021",
    "The official DiVA record diva2:1502080 identifies 'Abstractions to Control the Future' as a doctoral thesis published in 2021.",
    "https://uu.diva-portal.org/smash/record.jsf?pid=diva2%3A1502080",
)
manual_add(
    ["https://www.diva-portal.org/smash/get/diva2%3A780240/FULLTEXT02.pdf"],
    "2014",
    "The official DiVA record diva2:780240 identifies 'Functional Reactive Programming as programming model for telecom server software' as a thesis published in 2014.",
    "https://liu.diva-portal.org/smash/record.jsf?pid=diva2%3A780240",
)
manual_add(
    [
        "https://www.diva-portal.org/smash/get/diva2%3A991724/FULLTEXT01.pdf",
        "https://www.diva-portal.org/smash/get/diva2:991724/FULLTEXT01.pdf",
    ],
    "1999",
    "The official DiVA record diva2:991724 identifies 'Reactive objects and functional programming' as a doctoral thesis published in 1999.",
    "https://ltu.diva-portal.org/smash/record.jsf?pid=diva2%3A991724",
)

# Edinburgh Research Explorer records, supplemented by exact DOI or official
# proceedings metadata where an old Explorer slug no longer resolves.
manual_add(
    ["https://www.research.ed.ac.uk/files/12644250/haskml.pdf"],
    "2005",
    "The official Edinburgh record for the exact file identifies 'Functional programming languages for verification tools: a comparison of Standard ML and Haskell' and gives publication status Published, 2005.",
    "https://www.research.ed.ac.uk/en/publications/functional-programming-languages-for-verification-tools-a-compari/",
)
manual_add(
    ["https://www.research.ed.ac.uk/files/76099718/shallow_effect_handlers.pdf"],
    "2018-10-22",
    "The official Edinburgh record for the exact file says 'Shallow Effect Handlers' was e-published ahead of print on 22 October 2018.",
    "https://www.research.ed.ac.uk/en/publications/shallow-effect-handlers/",
)
manual_add(
    ["https://www.research.ed.ac.uk/en/publications/embedding-effect-systems-in-haskell/"],
    "2014-09-03",
    "Exact DOI metadata for 'Embedding effect systems in Haskell' (10.1145/2633357.2633368) gives both online and print publication as 03 September 2014.",
    "https://api.crossref.org/works/10.1145/2633357.2633368",
)
manual_add(
    ["https://www.research.ed.ac.uk/en/publications/notions-of-computation-and-monads/"],
    "1991-07",
    "Exact DOI metadata for 'Notions of computation and monads' (10.1016/0890-5401(91)90052-4) gives print publication in July 1991.",
    "https://api.crossref.org/works/10.1016/0890-5401(91)90052-4",
)
manual_add(
    ["https://www.research.ed.ac.uk/en/publications/computational-lambda-calculus-and-monads/"],
    "1989",
    "The official LICS 1989 proceedings index identifies 'Computational lambda-calculus and monads' in the 1989 symposium proceedings; no more precise publication date was exposed.",
    "https://lics.siglog.org/1989/Moggi-Computationallambda.html",
    confidence="medium",
)
manual_add(
    ["https://www.research.ed.ac.uk/en/publications/the-semantic-marriage-of-monads-and-effects/"],
    "2014-01-21",
    "The exact arXiv record for 'The semantic marriage of monads and effects' gives its first submission date as 21 January 2014.",
    "https://arxiv.org/abs/1401.5391",
    status="created",
)
manual_add(
    ["https://www.research.ed.ac.uk/en/publications/a-general-semantics-for-evaluation-logic/"],
    "1994",
    "The official LICS 1994 proceedings index lists 'A General Semantics for Evaluation Logic' in the 1994 proceedings; no more precise publication date was exposed.",
    "https://lics.siglog.org/1994/index.html",
    confidence="medium",
)
manual_add(
    ["https://www.research.ed.ac.uk/files/22099462/1_s2.0_S1571066106001666_main.pdf"],
    "2006-05",
    "The exact DOI metadata for 'Arrows, like Monads, are Monoids' (10.1016/j.entcs.2006.04.012), matching the Edinburgh file, gives print publication in May 2006.",
    "https://api.crossref.org/works/10.1016/j.entcs.2006.04.012",
)
manual_add(
    ["https://www.research.ed.ac.uk/files/286180994/Interaction_Trees_XIA_DOA14102019_VOR_CC_BY.pdf"],
    "2019-12-20",
    "The official Edinburgh record for the exact file says 'Interaction Trees: Representing Recursive and Impure Programs in Coq' was published 20 December 2019.",
    "https://www.research.ed.ac.uk/en/publications/interaction-trees-representing-recursive-and-impure-programs-in-c/",
)
manual_add(
    ["https://www.research.ed.ac.uk/files/24354309/haskell15_2.pdf"],
    "2015-08-30",
    "The official Edinburgh record for the exact file says 'Practical probabilistic programming with monads' was published 30 August 2015.",
    "https://www.research.ed.ac.uk/en/publications/practical-probabilistic-programming-with-monads/",
)

# Cambridge mappings that are unambiguous at the item or issue level.  Mutable
# first-view, collection, listing, and most-cited pages remain unresolved.
manual_add(
    [
        "https://www.cambridge.org/core/books/functional-programming-and-inputoutput?format=PB",
        "https://www.cambridge.org/as/universitypress/subjects/computer-science/programming-languages-and-applied-logic/functional-programming-and-inputoutput?format=PB",
        "https://www.cambridge.org/core/books/functional-programming-and-inputoutput/",
        "https://www.cambridge.org/us/academic/subjects/computer-science/programming-languages-and-applied-logic/functional-programming-and-inputoutput",
    ],
    "1994-09",
    "Cambridge bibliographic metadata identifies Andrew Gordon's 'Functional Programming and Input/Output' as first published in September 1994. The date refers to the work's original publication, not a later paperback listing.",
    "https://www.cambridge.org/core/books/functional-programming-and-inputoutput/",
    confidence="medium",
)
manual_add(
    ["https://www.cambridge.org/core/books/thinking-functionally-with-haskell/imperative-functional-programming/92EEB623AF7FB7EBEF6A7A00BFE7145"],
    "2014-11-05",
    "The Cambridge record for 'Thinking Functionally with Haskell' gives online publication on 05 November 2014; the target chapter URL contains a malformed content hash but uniquely names its chapter.",
    "https://www.cambridge.org/core/books/thinking-functionally-with-haskell/79F91D976F0C7229082325B41824EBBC",
    confidence="medium",
)
manual_add(
    [
        "https://www.cambridge.org/highereducation/books/the-haskell-school-of-expression/70651D70E17ECC07C91D8487D2EFEAE7",
        "https://www.cambridge.org/core/books/the-haskell-school-of-expression/",
        "https://www.cambridge.org/highereducation/product/70651D70E17ECC07C91D8487D2EFEAE7",
    ],
    "2000-02-28",
    "The official Cambridge product record for 'The Haskell School of Expression' gives the original print publication date as 28 February 2000; the later digital date is not used.",
    "https://www.cambridge.org/highereducation/books/the-haskell-school-of-expression/70651D70E17ECC07C91D8487D2EFEAE7",
)
manual_add(
    [
        "https://www.cambridge.org/core/journals/journal-of-functional-programming/issue/15F1C51D832FD7F084AE2602FBDB0157",
        "https://www.cambridge.org/core/journals/journal-of-functional-programming/issue/15F1C51D832FD7F084AE2602FBDB0157?pageNum=1",
        "https://www.cambridge.org/core/journals/journal-of-functional-programming/volume/15F1C51D832FD7F084AE2602FBDB0157",
    ],
    "2017",
    "The official Cambridge issue page identifies content hash 15F1C51D832FD7F084AE2602FBDB0157 as Journal of Functional Programming, Volume 27 (2017). The issue page has no single more precise date because its articles were published continuously.",
    "https://www.cambridge.org/core/journals/journal-of-functional-programming/issue/15F1C51D832FD7F084AE2602FBDB0157",
)
manual_add(
    ["https://www.cambridge.org/core/journals/journal-of-functional-programming/issue/DB5F4F2BDED65C6F89D84CF5213FA834"],
    "1998-07",
    "The official Cambridge issue page identifies this as Journal of Functional Programming, Volume 8, Issue 4, July 1998.",
    "https://www.cambridge.org/core/journals/journal-of-functional-programming/issue/DB5F4F2BDED65C6F89D84CF5213FA834",
)
manual_add(
    ["https://www.cambridge.org/core/journals/journal-of-functional-programming/volume/97FA87994DD90E812E2D11A36404D0D5"],
    "2025",
    "The official Cambridge HTML identifies this as Journal of Functional Programming, Volume 35, and exposes the issue-date year 2025.",
    "https://www.cambridge.org/core/journals/journal-of-functional-programming/volume/97FA87994DD90E812E2D11A36404D0D5",
)
manual_add(
    ["https://www.cambridge.org/core/journals/journal-of-functional-programming/issue/D59AB616739BEEF223327F3E4B7D762B"],
    "1993-01",
    "The official Cambridge HTML explicitly identifies this as Journal of Functional Programming, Volume 3, Issue 1, January 1993.",
    "https://www.cambridge.org/core/journals/journal-of-functional-programming/issue/D59AB616739BEEF223327F3E4B7D762B",
)
manual_add(
    ["https://www.cambridge.org/core/journals/journal-of-functional-programming/issue/E9F6A3ABEC907BAA7C2F1E8810106BA5"],
    "2008-07",
    "The official Cambridge HTML explicitly identifies this as Journal of Functional Programming, Volume 18, Issue 4, July 2008.",
    "https://www.cambridge.org/core/journals/journal-of-functional-programming/issue/E9F6A3ABEC907BAA7C2F1E8810106BA5",
)
manual_add(
    ["https://www.cambridge.org/core/journals/journal-of-functional-programming/volume/0FA3A396DEF84CFADE3FDA0B26D4CEE3"],
    "2008",
    "The official Cambridge HTML identifies this as Journal of Functional Programming, Volume 18; its issues are dated 2008.",
    "https://www.cambridge.org/core/journals/journal-of-functional-programming/volume/0FA3A396DEF84CFADE3FDA0B26D4CEE3",
)
manual_add(
    ["https://www.cambridge.org/core/product/20BF7DCA6330A2115C2C9B9BA47AB2E0"],
    "2025-01",
    "The exact target has a malformed Cambridge content hash. The corrected Cambridge article record identifies 'Automatically Testing Console I/O Behavior of Student Submissions in Haskell' in Journal of Functional Programming, Volume 35 (2025), with January 2025 article metadata.",
    "https://www.cambridge.org/core/journals/journal-of-functional-programming/article/automatically-testing-console-io-behavior-of-student-submissions-in-haskell/20BF7DCA6330A2115C2C2B9BA47AB2E0",
    confidence="medium",
)


def targets() -> list[str]:
    found: list[str] = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        if urlparse(fields[0]).hostname in HOSTS:
            found.append(fields[0])
    return found


def cache_json(name: str, url: str) -> dict | None:
    path = CACHE / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    response = SESSION.get(url, timeout=30)
    if response.status_code != 200:
        return None
    payload = response.json()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    time.sleep(0.08)
    return payload


def crossref(doi: str) -> dict | None:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", doi.lower())
    payload = cache_json(
        f"crossref-{safe}",
        f"https://api.crossref.org/works/{requests.utils.quote(doi, safe='')}",
    )
    if not payload or payload.get("status") != "ok":
        return None
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    if str(message.get("DOI", "")).lower() != doi.lower():
        return None
    return message


def date_parts(message: dict, key: str) -> str | None:
    value = message.get(key)
    if not isinstance(value, dict):
        return None
    parts = value.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return None
    numbers = parts[0]
    if not numbers or not 1 <= len(numbers) <= 3:
        return None
    return "-".join(
        [f"{numbers[0]:04d}"]
        + [f"{number:02d}" for number in numbers[1:]]
    )


def crossref_result(url: str, doi: str, message: dict) -> dict | None:
    # Prefer an explicit online-publication date, then a print-publication
    # date.  Fall back to the single Crossref published date only when neither
    # channel-specific field exists.
    choices = [
        ("published-online", "explicit online publication date"),
        ("published-print", "explicit print publication date"),
        ("published", "Crossref publication date"),
    ]
    for key, label in choices:
        value = date_parts(message, key)
        if value:
            title = " ".join(message.get("title") or [])
            return {
                "url": url,
                "old_status": "indexed",
                "old_date": "2026-07-27",
                "status": "publication",
                "source_type": "publication",
                "date": value,
                "new_date": value,
                "outcome": "resolved",
                "confidence": "high",
                "evidence": (
                    f"Crossref exact DOI {doi}; {label} ({key}) is {value}; "
                    f"title: {title}"
                ),
                "source_url": f"https://api.crossref.org/works/{doi}",
            }
    return None


def main() -> None:
    current = targets()
    results: list[dict] = []
    for url in current:
        host = urlparse(url).hostname
        record: dict | None = None
        if url in MANUAL:
            record = {
                "url": url,
                "old_status": "indexed",
                "old_date": "2026-07-27",
                **MANUAL[url],
                "new_date": MANUAL[url]["date"],
                "outcome": "resolved",
            }
        doi_match = DOI_RE.search(unquote(url))
        if record is None and host == "dl.acm.org" and doi_match:
            doi = doi_match.group(1).rstrip("/")
            message = crossref(doi)
            if message:
                record = crossref_result(url, doi, message)
        if record is None:
            blockers = {
                "dl.acm.org": (
                    "The ACM target is blocked by Cloudflare (HTTP 403), and its "
                    "legacy/publisher identifier has no exact DOI record in Crossref. "
                    "No source date was inferred from an identifier or search snippet."
                ),
                "repository.ubn.ru.nl": (
                    "The Radboud bitstream endpoint returns HTTP 403 and the associated "
                    "handle/metadata endpoint repeatedly times out, so the exact file "
                    "could not be joined to authoritative publication metadata."
                ),
                "www.diva-portal.org": (
                    "The DiVA full-text endpoint and central record lookup timed out, "
                    "and no exact official repository record for diva2:757286 was found."
                ),
                "www.research.ed.ac.uk": (
                    "The legacy Edinburgh publication slug no longer yields enough "
                    "metadata to identify the exact work unambiguously."
                ),
                "www.cambridge.org": (
                    "This Cambridge URL is a mutable aggregate page (FirstView, "
                    "collection, listing, or ranking), not a single publication with "
                    "one defensible creation/publication date."
                ),
            }
            record = {
                "url": url,
                "old_status": "indexed",
                "old_date": "2026-07-27",
                "outcome": "unresolved",
                "confidence": "none",
                "evidence": blockers.get(
                    host, "No defensible authoritative source date was found."
                ),
                "source_url": url,
            }
        results.append(record)

    assert len(results) == len(current)
    assert len({item["url"] for item in results}) == len(current)
    assert {item["url"] for item in results} == set(current)
    for item in results:
        if item["outcome"] == "resolved":
            assert item["status"] in {"publication", "created"}
            assert DATE_RE.fullmatch(item["date"])

    payload = {
        "generated": "2026-07-27",
        "method": (
            "Exact official publisher/repository records and exact DOI metadata; "
            "no dates inferred from URL identifier prefixes, search-index dates, "
            "or repository migration timestamps."
        ),
        "scope_hosts": sorted(HOSTS),
        "target_count": len(current),
        "resolved_count": sum(item["outcome"] == "resolved" for item in results),
        "unresolved_count": sum(item["outcome"] == "unresolved" for item in results),
        "summary": dict(Counter(item["outcome"] for item in results)),
        "per_host": {
            host: dict(
                Counter(
                    item["outcome"]
                    for item in results
                    if urlparse(item["url"]).hostname == host
                )
            )
            for host in sorted(HOSTS)
        },
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(payload["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
