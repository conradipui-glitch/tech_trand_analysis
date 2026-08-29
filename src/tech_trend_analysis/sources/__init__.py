"""Provider adapters that normalize external records into Observation objects."""

from .github_history import (
    GitHubHistoryClient,
    GitHubHistoryProtocolError,
    GitHubHistoryQuery,
    VerifiedGitEvent,
)
from .openalex import OpenAlexAdapter, OpenAlexProtocolError, OpenAlexQuery

__all__ = [
    "GitHubHistoryClient",
    "GitHubHistoryProtocolError",
    "GitHubHistoryQuery",
    "VerifiedGitEvent",
    "OpenAlexAdapter",
    "OpenAlexProtocolError",
    "OpenAlexQuery",
]
