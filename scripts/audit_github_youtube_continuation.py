#!/usr/bin/env python3
"""Audit current indexed GitHub and YouTube URLs in io_links.md.

Repository landing pages use the official GitHub REST API repository
``created_at`` timestamp.  A GitHub blob URL uses the oldest path-specific
commit returned by the official API, with the detailed commit response used to
verify that the file was added in that commit.

YouTube playlists are inspected with yt-dlp against the official page, but are
left unresolved unless the exact playlist contains one video.  Channel and
other collection pages have no single item date and are left unresolved.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "io_links.md"
REPORT = ROOT / "scratch" / "github-youtube-continuation-audit.json"
RAW_ROOT = ROOT / "scratch" / "github-youtube-continuation-raw"
GITHUB_RAW = RAW_ROOT / "github"
YOUTUBE_RAW = RAW_ROOT / "youtube"
TARGET_HOSTS = {"github.com", "www.youtube.com"}
DATE_RE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")
RESOLVED_STATUSES = {
    "archived",
    "created",
    "modified",
    "publication",
    "published",
    "updated",
    "uploaded",
}


def dump_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_targets() -> list[dict]:
    targets = []
    for line_number, line in enumerate(
        INPUT.read_text(encoding="utf-8").splitlines(), 1
    ):
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        url, status, date = fields
        if status != "indexed":
            continue
        host = urlparse(url).hostname
        if host in TARGET_HOSTS:
            targets.append(
                {
                    "url": url,
                    "line": line_number,
                    "old_status": status,
                    "old_date": date,
                    "host": host,
                }
            )
    return targets


def cache_name(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20] + ".json"


def run_json(command: list[str], timeout: int = 90) -> dict | list:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "_error": f"command exited {completed.returncode}",
            "_stderr": completed.stderr.strip()[-1500:],
            "_command": command,
        }
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {
            "_error": f"invalid JSON: {exc}",
            "_stderr": completed.stderr.strip()[-1500:],
            "_stdout": completed.stdout[-1500:],
            "_command": command,
        }


def cached_command(path: Path, command: list[str], timeout: int = 90) -> dict | list:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    payload = run_json(command, timeout=timeout)
    dump_json(path, payload)
    return payload


def github_repo_key(url: str) -> tuple[str, str] | None:
    parts = [piece for piece in urlparse(url).path.split("/") if piece]
    if len(parts) < 2 or parts[0].lower() == "topics":
        return None
    return parts[0], parts[1]


def fetch_repo(key: tuple[str, str]) -> dict | list:
    owner, repo = key
    cache = GITHUB_RAW / f"repo--{owner.lower()}--{repo.lower()}.json"
    return cached_command(cache, ["gh", "api", f"repos/{owner}/{repo}"])


def fetch_youtube_playlist(url: str) -> dict | list:
    cache = YOUTUBE_RAW / ("playlist--" + cache_name(url))
    return cached_command(
        cache,
        [
            "yt-dlp",
            "--flat-playlist",
            "--playlist-end",
            "2",
            "--dump-single-json",
            "--no-warnings",
            "--skip-download",
            url,
        ],
        timeout=120,
    )


def fetch_youtube_video(video_url: str) -> dict | list:
    cache = YOUTUBE_RAW / ("video--" + cache_name(video_url))
    return cached_command(
        cache,
        [
            "yt-dlp",
            "--dump-single-json",
            "--no-warnings",
            "--skip-download",
            video_url,
        ],
        timeout=120,
    )


def unresolved(target: dict, reason: str, evidence: str, **extra: object) -> dict:
    return {
        **{k: target[k] for k in ("url", "line", "old_status", "old_date")},
        "status": "unresolved",
        "outcome": "unresolved",
        "reason": reason,
        "evidence": evidence,
        **extra,
    }


def resolved(
    target: dict,
    status: str,
    date: str,
    evidence: str,
    source_url: str,
    **extra: object,
) -> dict:
    return {
        **{k: target[k] for k in ("url", "line", "old_status", "old_date")},
        "status": status,
        "date": date,
        "new_date": date,
        "outcome": "resolved",
        "confidence": "high",
        "evidence": evidence,
        "source_url": source_url,
        **extra,
    }


def audit_github(target: dict, repos: dict[tuple[str, str], dict | list]) -> dict:
    url = target["url"]
    parsed = urlparse(url)
    parts = [piece for piece in parsed.path.split("/") if piece]

    if len(parts) >= 2 and parts[0].lower() == "topics":
        return unresolved(
            target,
            "GitHub topic landing page has no single creation or publication date",
            "The exact URL is GitHub's continuously updated 'monad' topic collection, "
            "not a repository, release, commit, file, issue, or other single dated item.",
            source_url=url,
        )

    key = github_repo_key(url)
    if key is None:
        return unresolved(
            target,
            "GitHub URL could not be mapped to one repository",
            "The exact URL does not contain an owner/repository pair.",
            source_url=url,
        )
    owner, repo = key

    if len(parts) >= 5 and parts[2] == "blob":
        ref = parts[3]
        file_path = "/".join(parts[4:])
        history_cache = (
            GITHUB_RAW
            / f"commits-get--{owner.lower()}--{repo.lower()}--{cache_name(file_path)}"
        )
        history = cached_command(
            history_cache,
            [
                "gh",
                "api",
                "--method",
                "GET",
                "--paginate",
                "--slurp",
                "-f",
                f"path={file_path}",
                "-f",
                "per_page=100",
                f"repos/{owner}/{repo}/commits",
            ],
        )
        if isinstance(history, dict) and history.get("_error"):
            return unresolved(
                target,
                "GitHub file history API request failed",
                str(history.get("_stderr") or history.get("_error")),
                source_url=(
                    f"https://api.github.com/repos/{owner}/{repo}/commits"
                    f"?path={file_path}"
                ),
                requested_ref=ref,
            )
        pages = history if isinstance(history, list) else []
        commits = [
            item
            for page in pages
            if isinstance(page, list)
            for item in page
            if isinstance(item, dict) and item.get("sha")
        ]
        if not commits:
            return unresolved(
                target,
                "No path-specific GitHub commit history was returned",
                f"The official commits API returned no commits for {file_path!r}.",
                source_url=(
                    f"https://api.github.com/repos/{owner}/{repo}/commits"
                    f"?path={file_path}"
                ),
                requested_ref=ref,
            )
        oldest = commits[-1]
        sha = oldest["sha"]
        detail_cache = (
            GITHUB_RAW
            / f"commit--{owner.lower()}--{repo.lower()}--{sha[:16]}.json"
        )
        detail = cached_command(
            detail_cache,
            ["gh", "api", f"repos/{owner}/{repo}/commits/{sha}"],
        )
        if isinstance(detail, dict) and detail.get("_error"):
            return unresolved(
                target,
                "GitHub commit detail request failed",
                str(detail.get("_stderr") or detail.get("_error")),
                source_url=f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}",
                requested_ref=ref,
            )
        files = detail.get("files", []) if isinstance(detail, dict) else []
        exact_file = next(
            (
                item
                for item in files
                if isinstance(item, dict) and item.get("filename") == file_path
            ),
            None,
        )
        commit = oldest.get("commit", {})
        author = commit.get("author") or {}
        committer = commit.get("committer") or {}
        raw_date = author.get("date") or committer.get("date")
        file_status = exact_file.get("status") if exact_file else None
        if not raw_date or file_status != "added":
            return unresolved(
                target,
                "Oldest path-specific commit did not verify file creation",
                f"Oldest API commit is {sha}; exact file status was "
                f"{file_status!r} and author/committer date was {raw_date!r}.",
                source_url=f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}",
                requested_ref=ref,
                commit_sha=sha,
            )
        date = raw_date[:10]
        return resolved(
            target,
            "created",
            date,
            f"Official GitHub path-specific commit history identifies {sha} as the "
            f"oldest commit touching {file_path}; the detailed commit response marks "
            f"that exact file as 'added'. Its Git author timestamp is {raw_date}.",
            f"https://github.com/{owner}/{repo}/commit/{sha}",
            requested_ref=ref,
            file_path=file_path,
            commit_sha=sha,
            git_author_date=author.get("date"),
            git_committer_date=committer.get("date"),
        )

    if len(parts) != 2:
        return unresolved(
            target,
            "GitHub URL is not a repository landing page or supported single item",
            "The URL has additional path components and was not assigned the "
            "repository creation date.",
            source_url=url,
        )

    metadata = repos.get(key)
    if not isinstance(metadata, dict) or metadata.get("_error"):
        detail = (
            metadata.get("_stderr") or metadata.get("_error")
            if isinstance(metadata, dict)
            else "non-object API response"
        )
        return unresolved(
            target,
            "Official GitHub repository API did not return repository metadata",
            str(detail),
            source_url=f"https://api.github.com/repos/{owner}/{repo}",
        )
    created_at = metadata.get("created_at")
    if not isinstance(created_at, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T.*", created_at
    ):
        return unresolved(
            target,
            "Official GitHub repository metadata lacks a creation timestamp",
            f"The API response for {metadata.get('full_name') or f'{owner}/{repo}'} "
            f"has created_at={created_at!r}.",
            source_url=f"https://api.github.com/repos/{owner}/{repo}",
        )
    return resolved(
        target,
        "created",
        created_at[:10],
        f"Official GitHub REST repository metadata for "
        f"{metadata.get('full_name') or f'{owner}/{repo}'} gives "
        f"created_at={created_at}. The exact URL is a repository landing page, so "
        f"the repository creation date applies.",
        f"https://api.github.com/repos/{owner}/{repo}",
        canonical_url=metadata.get("html_url"),
        canonical_full_name=metadata.get("full_name"),
        github_created_at=created_at,
    )


def audit_youtube(target: dict, playlists: dict[str, dict | list]) -> dict:
    url = target["url"]
    parsed = urlparse(url)
    if parsed.path.startswith("/@") or parsed.path.startswith("/channel/"):
        return unresolved(
            target,
            "YouTube channel page has no single publication or upload date",
            "The exact URL identifies a continuously updated channel, not one video "
            "or other single dated item.",
            source_url=url,
        )
    if parsed.path != "/playlist":
        return unresolved(
            target,
            "YouTube URL is not an exact video page",
            "The exact URL does not identify one video with an upload date.",
            source_url=url,
        )

    playlist_id = (parse_qs(parsed.query).get("list") or [None])[0]
    metadata = playlists.get(url)
    if not isinstance(metadata, dict) or metadata.get("_error"):
        detail = (
            metadata.get("_stderr") or metadata.get("_error")
            if isinstance(metadata, dict)
            else "non-object extractor response"
        )
        return unresolved(
            target,
            "YouTube playlist metadata could not be retrieved",
            str(detail),
            source_url=url,
            playlist_id=playlist_id,
        )
    entries = [item for item in metadata.get("entries", []) if isinstance(item, dict)]
    count = metadata.get("playlist_count")
    if not isinstance(count, int):
        count = len(entries) if len(entries) < 2 else 2
    if count != 1:
        qualifier = (
            f"reports playlist_count={metadata.get('playlist_count')}"
            if metadata.get("playlist_count") is not None
            else f"returned {len(entries)} entries in a two-entry bounded probe"
        )
        return unresolved(
            target,
            "YouTube playlist is a multi-item or empty collection with no single date",
            f"Official-page metadata extracted by yt-dlp {qualifier}; a collection "
            f"modification timestamp is not a video publication/upload date.",
            source_url=url,
            playlist_id=playlist_id,
            playlist_title=metadata.get("title"),
            playlist_count=metadata.get("playlist_count"),
            playlist_modified_date=metadata.get("modified_date"),
            probed_video_ids=[item.get("id") for item in entries[:2]],
        )

    if len(entries) != 1 or not entries[0].get("id"):
        return unresolved(
            target,
            "Single-video playlist did not expose one exact video identifier",
            f"Playlist metadata reports one item but returned {len(entries)} usable "
            f"entry records.",
            source_url=url,
            playlist_id=playlist_id,
            playlist_title=metadata.get("title"),
        )
    video_id = entries[0]["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    video = fetch_youtube_video(video_url)
    if not isinstance(video, dict) or video.get("_error"):
        detail = (
            video.get("_stderr") or video.get("_error")
            if isinstance(video, dict)
            else "non-object extractor response"
        )
        return unresolved(
            target,
            "Exact video metadata for the one-item playlist could not be retrieved",
            str(detail),
            source_url=video_url,
            playlist_id=playlist_id,
            video_id=video_id,
        )
    upload_date = video.get("upload_date")
    if not isinstance(upload_date, str) or not re.fullmatch(r"\d{8}", upload_date):
        return unresolved(
            target,
            "Exact video metadata lacks an upload date",
            f"The one playlist video {video_id} has upload_date={upload_date!r}.",
            source_url=video_url,
            playlist_id=playlist_id,
            video_id=video_id,
        )
    date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    return resolved(
        target,
        "uploaded",
        date,
        f"The exact playlist contains one video ({video_id}); official-page video "
        f"metadata extracted by yt-dlp gives upload_date={upload_date}.",
        video_url,
        playlist_id=playlist_id,
        video_id=video_id,
        video_title=video.get("title"),
    )


def validate(targets: list[dict], results: list[dict]) -> None:
    target_urls = [item["url"] for item in targets]
    result_urls = [item["url"] for item in results]
    if len(target_urls) != len(set(target_urls)):
        raise ValueError("current target URLs are not unique")
    if len(result_urls) != len(set(result_urls)):
        raise ValueError("report result URLs are not unique")
    if set(target_urls) != set(result_urls):
        missing = sorted(set(target_urls) - set(result_urls))
        extra = sorted(set(result_urls) - set(target_urls))
        raise ValueError(f"coverage mismatch: missing={missing}, extra={extra}")
    for item in results:
        if item["status"] == "unresolved":
            if item.get("date"):
                raise ValueError(f"unresolved result has date: {item['url']}")
            if not item.get("reason") or not item.get("evidence"):
                raise ValueError(f"unresolved result lacks reason/evidence: {item['url']}")
            continue
        if item["status"] not in RESOLVED_STATUSES:
            raise ValueError(f"unsupported status {item['status']}: {item['url']}")
        if not DATE_RE.fullmatch(item.get("date", "")):
            raise ValueError(f"malformed date {item.get('date')!r}: {item['url']}")


def main() -> None:
    targets = load_targets()
    github_targets = [item for item in targets if item["host"] == "github.com"]
    youtube_targets = [
        item for item in targets if item["host"] == "www.youtube.com"
    ]

    repo_keys = {
        key
        for item in github_targets
        if (key := github_repo_key(item["url"])) is not None
    }
    repos: dict[tuple[str, str], dict | list] = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_keys = {executor.submit(fetch_repo, key): key for key in repo_keys}
        for future in as_completed(future_keys):
            repos[future_keys[future]] = future.result()

    playlist_urls = [
        item["url"]
        for item in youtube_targets
        if urlparse(item["url"]).path == "/playlist"
    ]
    playlists: dict[str, dict | list] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_urls = {
            executor.submit(fetch_youtube_playlist, url): url for url in playlist_urls
        }
        for future in as_completed(future_urls):
            playlists[future_urls[future]] = future.result()

    results = [audit_github(item, repos) for item in github_targets]
    results.extend(audit_youtube(item, playlists) for item in youtube_targets)
    results.sort(key=lambda item: item["line"])
    validate(targets, results)

    resolved_results = [
        item for item in results if item["status"] != "unresolved"
    ]
    unresolved_results = [
        item for item in results if item["status"] == "unresolved"
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": (
            "Official GitHub REST API repository created_at timestamps for exact "
            "repository landing pages; official path-specific commit history plus "
            "commit file status for GitHub blob creation; and yt-dlp extraction of "
            "official YouTube page metadata with collection pages unresolved unless "
            "they identify exactly one video."
        ),
        "target_count": len(targets),
        "github_target_count": len(github_targets),
        "youtube_target_count": len(youtube_targets),
        "resolved_count": len(resolved_results),
        "unresolved_count": len(unresolved_results),
        "results": results,
    }
    dump_json(REPORT, payload)
    raw_bytes = REPORT.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf") or b"\r\n" in raw_bytes:
        raise ValueError("report must be UTF-8 without BOM and use LF line endings")
    print(
        json.dumps(
            {
                "report": str(REPORT),
                "target_count": len(targets),
                "github_target_count": len(github_targets),
                "youtube_target_count": len(youtube_targets),
                "resolved_count": len(resolved_results),
                "unresolved_count": len(unresolved_results),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
