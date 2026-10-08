"""B-043: timestamp-safe supporting Git implementation activity.

This checks lineage *after* the technology already has a confirmed
same-SHA source-code anchor. It NEVER creates historical TrendState
observations, never changes first_seen, and never counts additional actors.
Repository metadata, filenames by themselves, docs/examples/tests, and
unverified merge history are not independent technological evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from .github_event_local_gate import evaluate_event_local
from .github_rename_lineage import trace_renamed_module
from .sources.github_history import GitHubHistoryClient, VerifiedGitEvent

_SOURCE = (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".cpp", ".c", ".h")
_EXCLUDED = re.compile(
    r"(?i)(^|/)(docs?|tests?|test|examples?|tutorials?|fixtures?|notebooks?|vendor|"
    r"node_modules|generated)/|(^|/)(test_[^/]*|[^/]*(_test|\.test|\.spec)\.[^/]+)$"
)


def _utc_timestamp(timestamp: str) -> datetime:
    value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Git event timestamps must have an explicit timezone")
    return value


def _source_file(path: str) -> bool:
    return path.lower().endswith(_SOURCE) and not _EXCLUDED.search(path)


def source_anchor_paths(source_diff: str | None) -> tuple[str, ...]:
    """Only executable-source FILE markers minted by our same-SHA collector."""
    if not source_diff:
        return ()
    paths = []
    for line in source_diff.splitlines():
        if line.startswith("FILE "):
            path = line[5:].strip()
            if _source_file(path):
                paths.append(path)
    return tuple(dict.fromkeys(paths))


@dataclass(frozen=True, slots=True)
class SupportingChangeResult:
    repository: str
    anchor_sha: str
    candidate_sha: str
    verdict: str                  # supporting | rejected | review_required
    reason: str
    source_paths: tuple[str, ...] = ()
    added_line_samples: tuple[str, ...] = ()
    original_anchor_timestamp: str | None = None
    candidate_timestamp: str | None = None
    verified_renames: tuple[tuple[str, str, str], ...] = ()

    @property
    def supporting(self) -> bool:
        return self.verdict == "supporting"


class GitModuleLineageVerifier:
    """Bounded same-repository source ancestry proof; no score-side effects."""

    def __init__(self, client: GitHubHistoryClient):
        self.client = client

    def verify(
        self,
        *,
        technology_direction: str,
        anchor: VerifiedGitEvent,
        candidate: VerifiedGitEvent,
    ) -> SupportingChangeResult:
        def reject(reason: str, verdict: str = "rejected") -> SupportingChangeResult:
            return SupportingChangeResult(
                anchor.repository, anchor.external_id, candidate.external_id,
                verdict, reason, original_anchor_timestamp=anchor.occurred_at,
                candidate_timestamp=candidate.occurred_at,
            )

        if anchor.repository != candidate.repository:
            return reject("cross_repository")
        if anchor.event_kind != "commit" or candidate.event_kind != "commit":
            return reject("only_commit_ancestry_supported")
        if anchor.external_id == candidate.external_id:
            return reject("same_commit_is_not_supporting_activity")
        if _utc_timestamp(candidate.occurred_at) <= _utc_timestamp(anchor.occurred_at):
            return reject("candidate_not_later_than_verified_anchor")
        paths = source_anchor_paths(anchor.source_diff)
        if not paths:
            return reject("no_verified_anchor_source_paths", "review_required")
        if not evaluate_event_local(
            technology_direction=technology_direction,
            title=anchor.title, text=anchor.evidence_text or anchor.title,
            source_diff=anchor.source_diff,
        ).eligible:
            return reject("anchor_not_technology_verified", "review_required")
        base_url = (
            f"/repos/{anchor.repository}/compare/"
            f"{quote(anchor.external_id, safe='')}...{quote(candidate.external_id, safe='')}"
        )
        comparison = self.client._get_json(base_url)
        # 'ahead' proves anchor is an ancestor of candidate; merely having
        # the same file path or an earlier date is not sufficient.
        if not isinstance(comparison, dict) or comparison.get("status") != "ahead":
            return reject("not_confirmed_descendant")
        commit_url = (
            f"/repos/{candidate.repository}/commits/"
            f"{quote(candidate.external_id, safe='')}"
        )
        details = self.client._get_json(commit_url)
        if not isinstance(details, dict) or details.get("sha") != candidate.external_id:
            return reject("candidate_commit_sha_mismatch")
        files = details.get("files")
        if not isinstance(files, list):
            return reject("missing_immutable_candidate_files", "review_required")

        # Current file path can diverge from the anchored path after a real
        # GitHub rename. Never infer a rename from spelling similarity.
        direct = any(
            isinstance(file, dict) and (
                file.get("filename") in paths
                or (file.get("status") == "renamed" and file.get("previous_filename") in paths)
            )
            for file in files[:60]
        )
        allowed_paths = set(paths)
        verified_renames: tuple[tuple[str, str, str], ...] = ()
        if not direct:
            resolution = trace_renamed_module(
                self.client, repository=anchor.repository,
                anchor_sha=anchor.external_id, candidate_sha=candidate.external_id,
                anchor_time=anchor.occurred_at, candidate_time=candidate.occurred_at,
                paths=paths,
            )
            if resolution.complete and resolution.steps:
                allowed_paths = set(resolution.paths)
                verified_renames = tuple(
                    (step.sha, step.from_path, step.to_path) for step in resolution.steps
                )
        matched_paths: list[str] = []
        samples: list[str] = []
        for item in files[:60]:
            if not isinstance(item, dict):
                continue
            new_path = str(item.get("filename") or "")
            old_path = str(item.get("previous_filename") or "")
            # Follow only explicit same-SHA GitHub renames; don't infer
            # identity merely from similarity of filenames.
            proven_rename = item.get("status") == "renamed" and old_path in allowed_paths
            if not _source_file(new_path) or not (new_path in allowed_paths or proven_rename):
                continue
            patch = item.get("patch")
            if not isinstance(patch, str):
                continue
            executable = [
                line[1:].strip()[:220]
                for line in patch.splitlines()
                if line.startswith("+") and not line.startswith("+++")
                and line[1:].strip()
                and not line[1:].lstrip().startswith(("#", "//", "*", "/*"))
            ]
            if not executable:
                continue
            # A broad helper file (utils.py, config.py, qa.py) may serve
            # unrelated features. Same filename alone must not certify a
            # technology-specific maintenance change.
            basename = new_path.rsplit("/", 1)[-1].casefold()
            technology_file = (
                bool(re.search(r"(?:lora|peft|adapter)", basename))
                if "lora" in technology_direction.casefold() or "low-rank" in technology_direction.casefold()
                else bool(re.search(r"(?:rag|retriev|vector|query)", basename))
            )
            family_lines = (
                re.compile(r"(?i)lora|peft|adapter")
                if "lora" in technology_direction.casefold() or "low-rank" in technology_direction.casefold()
                else re.compile(r"(?i)rag|retriev|vector|embedding|knowledge.graph")
            )
            if not technology_file and not any(family_lines.search(line) for line in executable):
                continue
            matched_paths.append(new_path)
            samples.extend(executable[:4])
        if not matched_paths:
            return reject("no_executable_changes_to_confirmed_module")
        return SupportingChangeResult(
            repository=anchor.repository,
            anchor_sha=anchor.external_id,
            candidate_sha=candidate.external_id,
            verdict="supporting",
            reason=("confirmed_ancestor_and_bounded_rename_chain"
                    if verified_renames else "confirmed_ancestor_and_same_module_source_change"),
            source_paths=tuple(dict.fromkeys(matched_paths)),
            verified_renames=verified_renames,
            added_line_samples=tuple(samples[:8]),
            original_anchor_timestamp=anchor.occurred_at,
            candidate_timestamp=candidate.occurred_at,
        )
