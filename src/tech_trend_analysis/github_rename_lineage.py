"""B-045: bounded, immutable GitHub source-rename ancestry.

Only the GitHub commit-details "renamed" status + previous_filename
can establish a path transition. Each hop must be a descendant of the
previous proof and an ancestor of the candidate. No fuzzy path matching,
branch-date shortcuts, current repository metadata or scoring effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode

from .sources.github_history import GitHubHistoryClient


@dataclass(frozen=True, slots=True)
class RenameStep:
    sha: str
    from_path: str
    to_path: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class RenameResolution:
    paths: tuple[str, ...]
    steps: tuple[RenameStep, ...]
    complete: bool
    reason: str


def _time(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("GitHub timestamp is missing timezone")
    return dt


def trace_renamed_module(
    client: GitHubHistoryClient,
    *,
    repository: str,
    anchor_sha: str,
    candidate_sha: str,
    anchor_time: str,
    candidate_time: str,
    paths: tuple[str, ...],
    candidate_paths: tuple[str, ...] = (),
    max_hops: int = 3,
    max_history: int = 40,
    max_commit_details: int = 12,
) -> RenameResolution:
    """Return only path transitions backed by a verified ancestry chain.

    A scoped history page at its cap is treated as incomplete, not as proof
    of "no rename." Any exhausted budget is fail-closed. The caller must
    still independently verify that the candidate changed executable
    technology-specific source code in the resolved path.
    """
    if not 1 <= max_hops <= 5 or not 2 <= max_history <= 100 or not 1 <= max_commit_details <= 30:
        raise ValueError("invalid bounded Git rename search budgets")
    start = _time(anchor_time)
    end = _time(candidate_time)
    if end <= start or not paths:
        return RenameResolution((), (), False, "invalid_rename_window")
    current = set(paths)
    transitions: list[RenameStep] = []
    cursor_sha, cursor_date = anchor_sha, start
    remaining = max_commit_details

    for _ in range(max_hops):
        transition: RenameStep | None = None
        # Candidate basenames influence *search order only*. They never
        # certify identity; every accepted path needs GitHub "renamed" proof.
        candidate_basenames = {p.rsplit("/", 1)[-1] for p in candidate_paths}
        ordered_paths = sorted(
            current, key=lambda p: (p.rsplit("/", 1)[-1] not in candidate_basenames, p)
        )
        for path in ordered_paths:
            query = urlencode({
                "path": path,
                "since": cursor_date.isoformat().replace("+00:00", "Z"),
                "until": end.isoformat().replace("+00:00", "Z"),
                "per_page": max_history,
                "page": 1,
            })
            history = client._get_json(f"/repos/{repository}/commits?{query}")
            if not isinstance(history, list):
                return RenameResolution(tuple(sorted(current)), tuple(transitions), False, "invalid_git_history")
            if len(history) >= max_history:
                return RenameResolution(tuple(sorted(current)), tuple(transitions), False, "truncated_git_history")
            for row in history:
                if not isinstance(row, dict):
                    continue
                sha = row.get("sha")
                if not isinstance(sha, str) or sha in (cursor_sha, candidate_sha):
                    continue
                stated = ((row.get("commit") or {}).get("committer") or {}).get("date")
                if not isinstance(stated, str) or not cursor_date < _time(stated) < end:
                    continue
                if remaining <= 0:
                    return RenameResolution(tuple(sorted(current)), tuple(transitions), False, "rename_budget_exhausted")
                remaining -= 1
                details = client._get_json(f"/repos/{repository}/commits/{quote(sha, safe='')}")
                if not isinstance(details, dict) or details.get("sha") != sha:
                    return RenameResolution(tuple(sorted(current)), tuple(transitions), False, "commit_sha_mismatch")
                event_at = ((details.get("commit") or {}).get("committer") or {}).get("date")
                if not isinstance(event_at, str) or not cursor_date < _time(event_at) < end:
                    continue
                for entry in details.get("files") or ():
                    if not isinstance(entry, dict) or entry.get("status") != "renamed":
                        continue
                    if entry.get("previous_filename") != path:
                        continue
                    new_path = entry.get("filename")
                    if not isinstance(new_path, str) or not new_path.endswith((".py",".ts",".tsx",".js",".rs",".go",".cpp",".c",".h")):
                        continue
                    # Both graph checks are necessary: a dated rename on
                    # another branch is NOT part of this module's ancestry.
                    left = client._get_json(
                        f"/repos/{repository}/compare/{quote(cursor_sha, safe='')}...{quote(sha, safe='')}"
                    )
                    right = client._get_json(
                        f"/repos/{repository}/compare/{quote(sha, safe='')}...{quote(candidate_sha, safe='')}"
                    )
                    if (not isinstance(left, dict) or left.get("status") != "ahead"
                            or not isinstance(right, dict) or right.get("status") != "ahead"):
                        continue
                    transition = RenameStep(sha, path, new_path, event_at)
                    break
                if transition is not None:
                    break
            if transition is not None:
                break

        if transition is None:
            # A bounded clean scan without a qualifying rename is a
            # negative finding, not permission to guess by file similarity.
            return RenameResolution(tuple(sorted(current)), tuple(transitions), True, "no_more_verified_renames")
        current.discard(transition.from_path)
        current.add(transition.to_path)
        transitions.append(transition)
        cursor_sha, cursor_date = transition.sha, _time(transition.occurred_at)
        # The candidate itself is already independently retrieved by SHA.
        # Once a verified chain reaches one of its changed source paths, do
        # not query hundreds of unrelated changes in the renamed module.
        if set(candidate_paths).intersection(current):
            return RenameResolution(tuple(sorted(current)), tuple(transitions), True, "candidate_path_reached")

    return RenameResolution(tuple(sorted(current)), tuple(transitions), False, "max_rename_hops_reached")
