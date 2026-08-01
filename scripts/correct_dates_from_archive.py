#!/usr/bin/env python3
"""Extract ranked authored/publication dates from the local full-link archive."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup
from dateutil import parser as date_parser


YEAR = re.compile(r"\b(18\d{2}|19\d{2}|20\d{2})\b")
FULL_DATES = (
    re.compile(r"\b(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[,.]?\s+\d{4})\b", re.I),
    re.compile(r"\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4})\b", re.I),
    re.compile(r"\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})\b", re.I),
    re.compile(r"\b((?:18|19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2})\b"),
)
COURSE_YEAR = re.compile(r"(?:^|[/_-])(?:fall|autumn|spring|winter|summer|fa|sp|wi|su)[-_]?(\d{2}|20\d{2})(?:[/_.-]|$)", re.I)
PATH_YEAR = re.compile(r"(?:^|[/_-])((?:19|20)\d{2})(?:[/_.-]|$)")
DOI_YEAR = re.compile(r"10\.\d{4,9}/[^?#]*(19\d{2}|20\d{2})", re.I)
ACADEMIC_PAIR = re.compile(r"(?:^|/)(?:teaching|courses?|lecture[^/]*)/(\d{2})(\d{2})(?:/|$)", re.I)
DBLP_ARXIV = re.compile(r"/abs-(\d{2})(\d{2})-\d+\.html$", re.I)
PUBLISHED_KEYS = {
    "article:published_time", "datepublished", "citation_publication_date",
    "citation_date", "dc.date.issued", "dcterms.issued", "publication_date",
    "publishdate", "pubdate", "date.issued",
}
CREATED_KEYS = {"datecreated", "date_created", "dc.date.created", "dcterms.created"}
MODIFIED_KEYS = {"article:modified_time", "datemodified", "last-modified", "last_modified"}

# Narrow corrections for records whose downloaded content or bibliographic identity
# gives a date that the generic extractor cannot safely infer.  Inaccessible Radboud
# PDFs retain an honest access date instead of treating repository namespace 2066 as
# a creation year.
MANUAL_DATES: dict[str, tuple[str, str, str]] = {
    "https://ci.nii.ac.jp/ncid/BA57122249": ("publication", "1970", "catalogue date [197-?]"),
    "https://natlib.govt.nz/records/20523671?search%5Bi%5D%5Bcentury%5D=1900&search%5Bi%5D%5Bcreator%5D=Burgess%2C+Peter%2C+1964-&search%5Bpage%5D=1&search%5Bpath%5D=items&search%5Btext%5D=North%2C+Nigel": ("accessed", "2026-07-27", "1900 is a search-filter value, not the record date"),
    "https://citeseerx.ist.psu.edu/document?doi=94030f2d0b1fb28f8b1909ee748892573de294bb&repid=rep1&type=pdf": ("accessed", "2026-07-27", "1909 is part of a hash, not the document date"),
    "https://www.cl.cam.ac.uk/teaching//1920/Types/handout.pdf": ("created", "2019", "2019/20 course path"),
    "https://webarchive.di.uminho.pt/wiki.di.uminho.pt/twiki/pub/Education/CP/MaterialPedagogico/cp1920f12.pdf": ("created", "2019", "PDF states 2019/20"),
    "https://www.imperial.ac.uk/media/imperial-college/faculty-of-engineering/computing/public/1920-ug-projects/An-Investigation-into-Adding-Exception-Handling-to-Haskell.pdf": ("created", "2020", "2019/20 undergraduate project"),
    "https://dblp.org/rec/journals/corr/abs-2303-01350.html": ("published", "2023-03", "arXiv identifier"),
    "https://dblp.org/rec/journals/corr/abs-2211-06863.html": ("published", "2022-11", "arXiv identifier"),
    "https://dblp1.uni-trier.de/pid/15/1957.html": ("published", "1990", "earliest listed publication"),
    "https://effective-haskell.com/chapters/table-of-contents.html": ("published", "2023", "page copyright/byline"),
    "https://effective-haskell.com/chapters/chapter7.html": ("published", "2023", "page copyright/byline"),
    "https://f6.erista.me/files/bitsavers/pdf/xerox/parc/techReports/CSL-91-12_CSL_Technical_Reports_Digest_1973-1991_199111.pdf": ("published", "1991-11", "report filename and coverage"),
    "https://livevideo.manning.com/module/2028_16_3/haskell-in-depth-video-edition/concurrency/summary?fullscreen=true": ("published", "2021-05", "book publication"),
    "https://rockthejvm.com/podcast/b588fa07-2087-401d-9d1e-fb53e51d8ba1": ("published", "2026-04-16", "displayed episode date"),
    "https://iris.unito.it/bitstream/2318/1739403/1/main.pdf": ("published", "2020", "repository cover and DOI publication"),
    "https://pure.uva.nl/ws/files/2217978/167002_haskell_for_ocaml_programmers.pdf": ("published", "2014-03", "repository cover and document title page"),
    "https://mirrors.tuna.tsinghua.edu.cn/help/hackage/": ("updated", "2026-07-26", "generated help-page metadata"),
    "https://repository.ubn.ru.nl/bitstream/2066/111084/1/111084.pdf": ("accessed", "2026-07-27", "download failed; 2066 is repository namespace"),
    "https://repository.ubn.ru.nl/bitstream/handle/2066/306183/306183.pdf?isAllowed=y&sequence=1": ("accessed", "2026-07-27", "download failed; 2066 is repository namespace"),
    "https://repository.ubn.ru.nl/bitstream/handle/2066/224622/1/224622.pdf": ("accessed", "2026-07-27", "download failed; 2066 is repository namespace"),
    "https://repository.ubn.ru.nl/bitstream/handle/2066/18841/18841_tutotothc.pdf": ("accessed", "2026-07-27", "download failed; 2066 is repository namespace"),
    "https://repository.ubn.ru.nl/bitstream/handle/2066/161445/161445.pdf?isAllowed=y&sequence=1": ("accessed", "2026-07-27", "download failed; 2066 is repository namespace"),
}


def normalized_date(value: str) -> str | None:
    value = value.strip()
    match = YEAR.search(value)
    if not match:
        return None
    year = int(match.group(1))
    if year < 1800 or year > date.today().year:
        return None
    try:
        parsed = date_parser.parse(value, fuzzy=True, default=datetime(year, 1, 1))
    except (ValueError, OverflowError, TypeError):
        return str(year)
    if parsed.year != year:
        return str(year)
    has_day = bool(re.search(r"\b\d{1,2}\b", value.replace(str(year), "")))
    has_month = bool(re.search(r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|(?:[-/]\d{1,2})", value, re.I))
    if has_day and has_month:
        return parsed.strftime("%Y-%m-%d")
    if has_month:
        return parsed.strftime("%Y-%m")
    return str(year)


def candidate(value: str, kind: str, priority: int, source: str) -> dict[str, object] | None:
    result = normalized_date(value)
    return {"date": result, "kind": kind, "priority": priority, "source": source, "raw": value[:200]} if result else None


def json_dates(value: object, output: list[dict[str, object]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).casefold()
            if isinstance(item, str):
                if lowered in PUBLISHED_KEYS:
                    found = candidate(item, "published", 1, f"json:{key}")
                    if found: output.append(found)
                elif lowered in CREATED_KEYS:
                    found = candidate(item, "created", 2, f"json:{key}")
                    if found: output.append(found)
                elif lowered in MODIFIED_KEYS:
                    found = candidate(item, "modified", 7, f"json:{key}")
                    if found: output.append(found)
            json_dates(item, output)
    elif isinstance(value, list):
        for item in value:
            json_dates(item, output)


def html_candidates(path: Path) -> list[dict[str, object]]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    output: list[dict[str, object]] = []
    for meta in soup.find_all("meta"):
        key = str(meta.get("property") or meta.get("name") or meta.get("itemprop") or "").casefold()
        value = str(meta.get("content") or "")
        if key in PUBLISHED_KEYS:
            found = candidate(value, "published", 1, f"meta:{key}")
        elif key in CREATED_KEYS:
            found = candidate(value, "created", 2, f"meta:{key}")
        elif key in MODIFIED_KEYS:
            found = candidate(value, "modified", 7, f"meta:{key}")
        else:
            found = None
        if found: output.append(found)
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try: json_dates(json.loads(script.get_text()), output)
        except (json.JSONDecodeError, TypeError): pass
    for element in soup.find_all("time"):
        value = str(element.get("datetime") or element.get_text(" ", strip=True))
        found = candidate(value, "published", 3, "time")
        if found: output.append(found)
    for unwanted in soup(["script", "style", "noscript", "svg", "template"]):
        unwanted.decompose()
    text = " ".join(soup.stripped_strings)[:12000]
    labelled = re.compile(r"(?:published|publication|posted|written|authored|created|released|date)\s*(?:on|:)?\s*([^|;]{0,60})", re.I)
    for match in labelled.finditer(text[:6000]):
        found = candidate(match.group(1), "published", 3, "visible-labelled")
        if found: output.append(found)
    for pattern in FULL_DATES:
        for match in pattern.finditer(text[:4000]):
            found = candidate(match.group(1), "published", 4, "visible-date")
            if found: output.append(found)
    return output


def pdf_candidates(path: Path) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as directory:
        text_path = Path(directory) / "first-pages.txt"
        result = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "2", "-enc", "UTF-8", str(path), str(text_path)],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0 and text_path.exists():
            text = text_path.read_text(encoding="utf-8", errors="ignore")[:12000]
            for pattern in FULL_DATES:
                for match in pattern.finditer(text[:6000]):
                    found = candidate(match.group(1), "published", 4, "pdf-front-date")
                    if found: output.append(found)
            labelled = re.compile(r"(?:published|publication|copyright|©|submitted|thesis|dissertation)\D{0,40}((?:18|19|20)\d{2})", re.I)
            for match in labelled.finditer(text[:8000]):
                found = candidate(match.group(1), "published", 5, "pdf-front-labelled-year")
                if found: output.append(found)
    return output


def url_candidates(url: str) -> list[dict[str, object]]:
    decoded = unquote(urlsplit(url).path)
    output = []
    for match in COURSE_YEAR.finditer(decoded):
        raw = match.group(1)
        year = int(raw)
        if year < 100:
            year += 2000 if year <= date.today().year % 100 else 1900
        output.append({"date": str(year), "kind": "created", "priority": 3, "source": "url-course-year", "raw": match.group(0)})
    for match in ACADEMIC_PAIR.finditer(decoded):
        first, second = int(match.group(1)), int(match.group(2))
        if (first + 1) % 100 == second:
            year = 2000 + first if first < 80 else 1900 + first
            output.append({"date": str(year), "kind": "created", "priority": 3, "source": "url-academic-year", "raw": match.group(0)})
    for match in PATH_YEAR.finditer(decoded):
        if int(match.group(1)) <= date.today().year:
            output.append({"date": match.group(1), "kind": "created", "priority": 6, "source": "url-year", "raw": match.group(0)})
    arxiv = DBLP_ARXIV.search(decoded)
    if arxiv:
        year = 2000 + int(arxiv.group(1))
        month = int(arxiv.group(2))
        if 1 <= month <= 12 and year <= date.today().year:
            output.append({"date": f"{year:04d}-{month:02d}", "kind": "published", "priority": 0, "source": "url-arxiv-id", "raw": arxiv.group(0)})
    return output


def year_of(value: str) -> int | None:
    match = YEAR.search(value)
    return int(match.group(1)) if match else None


def near_today(value: str) -> bool:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return False
    return abs(parsed - date.today()) <= timedelta(days=7)


def choose_evidence(
    url: str,
    row: list[str],
    evidence: list[dict[str, object]],
    item: dict[str, object] | None,
) -> dict[str, object] | None:
    old_year = year_of(row[2])
    suspicious = old_year is None or old_year < 1980 or old_year >= date.today().year
    host = (urlsplit(url).hostname or "").casefold()
    path = unquote(urlsplit(url).path).casefold()
    articleish = any(token in path for token in ("/blog/", "/blogs/", "/post/", "/posts/", "/article/", "/articles/"))
    media = str((item or {}).get("content_type", "")).casefold()
    actual_pdf = "application/pdf" in media

    reliable = []
    for value in evidence:
        source = str(value["source"])
        if source.startswith("meta:citation_") or source in {
            "meta:article:published_time", "meta:dc.date.issued",
            "meta:dcterms.issued", "meta:date.issued", "meta:datepublished",
        }:
            reliable.append(value)
        elif source == "json:datePublished" and "dblp" not in host:
            corroborated = any(
                other is not value
                and str(other["source"]) != "json:datePublished"
                and year_of(str(other["date"])) == year_of(str(value["date"]))
                for other in evidence
            )
            if articleish or corroborated:
                reliable.append(value)
    if reliable:
        source_rank = {
            "meta:citation_publication_date": 0,
            "meta:citation_date": 0,
            "meta:article:published_time": 1,
            "meta:datepublished": 1,
            "json:datePublished": 2,
            "meta:dc.date.issued": 3,
            "meta:dcterms.issued": 3,
            "meta:date.issued": 3,
        }
        selected = min(
            reliable,
            key=lambda value: (
                source_rank.get(str(value["source"]), 9),
                -str(value["date"]).count("-"),
            ),
        )
        doi_match = DOI_YEAR.search(unquote(url))
        if doi_match and abs(int(doi_match.group(1)) - (year_of(str(selected["date"])) or 0)) > 2:
            return None
        return selected

    course = [value for value in evidence if str(value["source"]) in {"url-course-year", "url-academic-year"}]
    if course:
        course_year = year_of(str(course[0]["date"]))
        corroborating = [
            value for value in evidence
            if str(value["source"]) in {"visible-date", "pdf-front-date"}
            and year_of(str(value["date"])) == course_year
        ]
        if corroborating:
            return max(corroborating, key=lambda value: str(value["date"]).count("-"))
        return course[0]

    if actual_pdf:
        front = [
            value for value in evidence
            if str(value["source"]) == "pdf-front-date"
            and not near_today(str(value["date"]))
        ]
        if front and (suspicious or year_of(str(front[0]["date"])) == old_year):
            return front[0]
        labelled = [value for value in evidence if str(value["source"]) == "pdf-front-labelled-year"]
        if labelled and suspicious:
            return labelled[0]

    times = [value for value in evidence if str(value["source"]) == "time"]
    if times and articleish:
        path_years = {year_of(str(value["date"])) for value in evidence if str(value["source"]) == "url-year"}
        matching = [value for value in times if year_of(str(value["date"])) in path_years] if path_years else times
        if matching:
            return matching[0]

    if articleish and suspicious:
        visible = [value for value in evidence if str(value["source"]) == "visible-date"]
        unique = {str(value["date"]) for value in visible}
        if len(unique) == 1:
            return visible[0]

    url_years = [value for value in evidence if str(value["source"]) == "url-year"]
    if suspicious and url_years:
        plausible = [value for value in url_years if (year_of(str(value["date"])) or 0) >= 1980]
        if plausible:
            return plausible[0]
    return None


def extract(url: str, item: dict[str, object], archive: Path) -> dict[str, object]:
    path = archive / str(item.get("file", ""))
    candidates = url_candidates(url)
    if not path.exists():
        return {"candidates": candidates, "error": "missing_file"}
    media = str(item.get("content_type", "")).casefold()
    try:
        prefix = path.read_bytes()[:8]
        if "html" in media or path.suffix.casefold() in {".html", ".htm"}:
            candidates.extend(html_candidates(path))
        elif "pdf" in media or prefix.startswith(b"%PDF"):
            candidates.extend(pdf_candidates(path))
    except (OSError, subprocess.SubprocessError) as exc:
        return {"candidates": candidates, "error": type(exc).__name__}
    candidates.sort(key=lambda item: (item["priority"], -str(item["date"]).count("-")))
    return {"candidates": candidates}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument("--archive", type=Path, default=Path("tmp/io-links-full-download"))
    parser.add_argument("--cache", type=Path, default=Path("tmp/io-links-full-download/date-evidence.json"))
    parser.add_argument("--report", type=Path, default=Path("tmp/io-links-full-download/date-corrections.json"))
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    http = json.loads((args.archive / "manifest-latest.json").read_text(encoding="utf-8"))
    browser_path = args.archive / "browser-manifest-latest.json"
    browser = json.loads(browser_path.read_text(encoding="utf-8")) if browser_path.exists() else {}
    effective = {url: item for url, item in http.items() if item.get("state") == "ok"}
    effective.update({url: item for url, item in browser.items() if item.get("state") == "ok"})
    final_targets: dict[str, list[str]] = {}
    for url, item in effective.items():
        final = str(item.get("final_url", url)).rstrip("/")
        final_targets.setdefault(final, []).append(url)
    excluded_redirects = {
        url
        for final, urls in final_targets.items()
        if len(urls) > 1
        for url in urls
        if url.rstrip("/") != final
    }
    for url, item in list(effective.items()):
        original = urlsplit(url)
        final = urlsplit(str(item.get("final_url", url)))
        if (
            original.path.rstrip("/")
            and (original.hostname or "").casefold() != (final.hostname or "").casefold()
            and final.path.rstrip("/").casefold() in {"", "/home", "/research", "/en-us/research"}
        ):
            excluded_redirects.add(url)
    effective = {url: item for url, item in effective.items() if url not in excluded_redirects}
    cache = json.loads(args.cache.read_text(encoding="utf-8")) if args.cache.exists() else {}
    pending = [url for url, item in effective.items() if cache.get(url, {}).get("sha256") != item.get("sha256")]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(extract, url, effective[url], args.archive): url for url in pending}
        for count, future in enumerate(as_completed(futures), 1):
            url = futures[future]
            result = future.result()
            result["sha256"] = effective[url].get("sha256")
            cache[url] = result
            if count % 250 == 0:
                args.cache.write_text(json.dumps(cache, sort_keys=True) + "\n", encoding="utf-8")
                print({"extracted_now": count, "remaining": len(pending) - count}, flush=True)
    args.cache.write_text(json.dumps(cache, sort_keys=True) + "\n", encoding="utf-8")

    lines = args.file.read_text(encoding="utf-8").splitlines()
    rows = [line.split("\t") for line in lines[1:] if len(line.split("\t")) == 3]
    proposals = []
    replacements: dict[str, list[str]] = {}
    for row in rows:
        url, old_kind, old_date = row
        if url in MANUAL_DATES:
            new_kind, new_date, source = MANUAL_DATES[url]
            if [new_kind, new_date] != [old_kind, old_date]:
                replacement = [url, new_kind, new_date]
                replacements[url] = replacement
                proposals.append({"old": row, "new": replacement, "evidence": {"source": "manual", "raw": source}})
            continue
        evidence = list(cache.get(url, {}).get("candidates", []))
        existing_url_evidence = {(str(value["source"]), str(value["raw"])) for value in evidence}
        evidence.extend(
            value for value in url_candidates(url)
            if (str(value["source"]), str(value["raw"])) not in existing_url_evidence
        )
        evidence.sort(key=lambda item: (item["priority"], -str(item["date"]).count("-")))
        if not evidence:
            continue
        best = choose_evidence(url, row, evidence, effective.get(url))
        if best is None:
            continue
        old_year_match = YEAR.search(old_date)
        old_year = int(old_year_match.group(1)) if old_year_match else None
        if best["date"] == old_date and best["kind"] == old_kind:
            continue
        new_kind = str(best["kind"])
        if best["date"] == old_date and old_kind in {"uploaded", "released", "authored", "publication"}:
            new_kind = old_kind
        replacement = [url, new_kind, str(best["date"])]
        replacements[url] = replacement
        proposals.append({"old": row, "new": replacement, "evidence": best, "alternatives": [value for value in evidence if value is not best][:5]})
    report = {"downloaded_items": len(effective), "extracted_now": len(pending), "proposals": len(proposals), "changes": proposals}
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.apply:
        output = [replacements.get(row[0], row) for row in rows]
        output.sort(key=lambda row: row[2])
        args.file.write_text("\n".join([lines[0], *("\t".join(row) for row in output)]) + "\n", encoding="utf-8", newline="\n")
    print({key: value for key, value in report.items() if key != "changes"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
