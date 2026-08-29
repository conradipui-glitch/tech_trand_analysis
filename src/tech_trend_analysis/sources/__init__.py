"""Provider adapters that normalize external records into Observation objects."""

from .github import GitHubAdapter, GitHubProtocolError, GitHubQuery, GitHubRepositoryCandidate
from .github_history import (
    GitHubHistoryClient,
    GitHubHistoryProtocolError,
    GitHubHistoryQuery,
    VerifiedGitEvent,
)
from .openalex import OpenAlexAdapter, OpenAlexProtocolError, OpenAlexQuery

__all__ = [
    "GitHubAdapter",
    "GitHubProtocolError",
    "GitHubQuery",
    "GitHubRepositoryCandidate",
    "GitHubHistoryClient",
    "GitHubHistoryProtocolError",
    "GitHubHistoryQuery",
    "VerifiedGitEvent",
    "OpenAlexAdapter",
    "OpenAlexProtocolError",
    "OpenAlexQuery",
]
