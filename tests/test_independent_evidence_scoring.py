"""B-037 regression: raw activity is not multiple independent adopters."""
from __future__ import annotations

import unittest
from datetime import date

from tech_trend_analysis.clustering import Microcluster, MicroclusterConfig, MicroclusteringResult
from tech_trend_analysis.independent_evidence import independent_unit
from tech_trend_analysis.scoring import EmergingScorer, _score_independent_projection
from tech_trend_analysis.trend_state import TrendStateManager


DIRECTION = "low-rank adaptation of large language models"
AS_OF = date(2026, 10, 9)
CONFIG = MicroclusterConfig("agglomerative_average_cosine", 0.4, calibration="test")


def obs(oid, *, repo=None, kind="repository", published=None, observed="2026-09-01T00:00:00Z",
        verified=False, provider="github", evidence="implementation", actor="alice"):
    source = {
        "observation_id": oid, "provider": provider, "evidence_type": evidence,
        "artifact_kind": kind, "published_at": published, "observed_at": observed,
        "actors": [{"kind": "organization", "name": actor, "external_id": actor}],
        "collection_context": {"technology_direction": DIRECTION, "source_profile": "software_ai"},
    }
    if provider == "github":
        if kind == "repository":
            source["external_id"] = repo
        else:
            source["external_id"] = f"{repo}:{kind}:{oid}"
            source["relationships"] = [{"type": "belongs_to_repository", "target_id": "github:" + repo}]
        source["quality_flags"] = {"historical_timestamp_verified": verified}
    return source


def batch(*clusters):
    return MicroclusteringResult(
        profile="software_ai", config=CONFIG, embedding_model="BAAI/bge-m3",
        clusters=tuple(clusters), assignments={
            oid: cluster.cluster_id for cluster in clusters for oid in cluster.member_ids
        },
    )


def ingest(manager, name, observations):
    member_ids = tuple(observations)
    cluster = Microcluster(f"micro:{name}", member_ids, (1.0, 0.0), len(member_ids))
    return manager.ingest(batch(cluster), observations, now="2026-10-09T00:00:00Z")


class IndependentGitHubScoringTests(unittest.TestCase):
    def initial_state(self):
        manager = TrendStateManager()
        repo = obs("github:alice/lora", repo="alice/lora", observed="2026-09-01T00:00:00Z")
        research = obs("openalex:W42", kind="paper", published="2025-12-01T00:00:00Z",
                       provider="openalex", evidence="research", actor="research-lab")
        result = ingest(manager, "first", {r["observation_id"]: r for r in (repo, research)})
        return manager, result.created_trend_ids[0], repo

    def append(self, manager, repo, name, date_, *, verified=True):
        event = obs(f"github:alice/lora:commit:{name}", repo="alice/lora", kind="commit",
                    published=date_, observed="2026-10-01T00:00:00Z",
                    actor="numeric-owner-id", verified=verified)
        ingest(manager, name, {repo["observation_id"]: repo, event["observation_id"]: event})
        return event

    def test_github_repo_many_commits_still_one_effective_evidence(self):
        manager, trend_id, repo = self.initial_state()
        scorer = EmergingScorer()
        state = manager.states[trend_id]
        self.assertEqual(2, state.observation_count)
        self.assertEqual(2, len(state.independent_units))
        first = self.append(manager, repo, "early", "2026-01-15T00:00:00Z")
        self.assertEqual(3, state.observation_count)
        after_first = scorer.score(state, as_of=AS_OF)
        self.assertEqual(2, len(state.independent_units))
        self.assertEqual(1, _score_independent_projection(state).evidence_counts["implementation"])
        self.assertEqual("2026-01-15T00:00:00Z",
                         _score_independent_projection(state).first_evidence_at["implementation"])
        self.assertEqual(1, _score_independent_projection(state).periods["2026-01"].total)
        self.assertNotIn("2026-09", _score_independent_projection(state).periods)
        self.assertEqual(1, sum(k.startswith("github:owner:") for k in
                                _score_independent_projection(state).actor_keys))

        self.append(manager, repo, "later", "2026-03-01T00:00:00Z")
        self.append(manager, repo, "latest", "2026-08-01T00:00:00Z")
        after_many = scorer.score(state, as_of=AS_OF)
        self.assertEqual(5, state.observation_count)
        self.assertEqual(2, len(state.independent_units))
        self.assertEqual(after_first.total, after_many.total)
        self.assertEqual(after_first.confidence, after_many.confidence)
        self.assertEqual(after_first.stage, after_many.stage)
        self.assertEqual("2026-01-15T00:00:00Z",
                         state.independent_units["github:repo:alice/lora"].event_time)
        # The raw evidence (including all URLs) is deliberately preserved.
        self.assertEqual(5, len(state.observation_ids))

        replay = ingest(manager, "replay", {repo["observation_id"]: repo, first["observation_id"]: first})
        self.assertEqual(0, replay.assignments[0].new_observation_count)
        self.assertEqual(after_many.total, scorer.score(state, as_of=AS_OF).total)

    def test_earlier_verified_event_replaces_later_but_not_duplicate_count(self):
        manager, trend_id, repo = self.initial_state()
        self.append(manager, repo, "late", "2026-05-01T00:00:00Z")
        self.append(manager, repo, "early", "2026-01-01T00:00:00Z")
        effective = _score_independent_projection(manager.states[trend_id])
        self.assertEqual("2026-01-01T00:00:00Z", effective.first_evidence_at["implementation"])
        self.assertEqual(2, effective.observation_count)
        self.assertNotIn("2026-05", effective.periods)
        self.assertEqual(2, len(manager.states[trend_id].independent_units))

    def test_two_repositories_same_owner_are_two_units_one_actor(self):
        manager, trend_id, repo = self.initial_state()
        repo_two = obs("github:alice/other", repo="alice/other")
        ingest(manager, "second-repo", {repo_two["observation_id"]: repo_two})
        state = manager.states[trend_id]
        self.assertEqual(3, len(state.independent_units))
        effective = _score_independent_projection(state)
        self.assertEqual(2, effective.evidence_counts["implementation"])
        self.assertEqual(2, effective.actor_diversity)  # github:alice + research-lab
        self.assertEqual(3, effective.observation_count)

    def test_unverified_git_event_cannot_backdate_scoring_first_seen(self):
        manager, trend_id, repo = self.initial_state()
        self.append(manager, repo, "spoof", "2019-01-01T00:00:00Z", verified=False)
        effective = _score_independent_projection(manager.states[trend_id])
        self.assertEqual("2026-09-01T00:00:00Z", effective.first_evidence_at["implementation"])
        self.assertEqual("2025-12-01T00:00:00Z", effective.first_seen)

    def test_unlinked_commit_cannot_claim_independent_repository(self):
        commit = obs("github:no-provenance", repo="alice/lora", kind="commit",
                     published="2026-02-01T00:00:00Z", verified=True)
        commit.pop("relationships")
        with self.assertRaisesRegex(ValueError, "belongs_to_repository"):
            independent_unit(commit, event_time="2026-02-01T00:00:00Z", actor_keys=set())

    def test_separate_providers_keep_distinct_research_evidence(self):
        manager, trend_id, _ = self.initial_state()
        paper2=obs("openalex:W43", kind="paper", provider="openalex",
                   published="2026-03-03T00:00:00Z", evidence="research", actor="other-lab")
        ingest(manager, "paper2", {paper2["observation_id"]: paper2})
        effective = _score_independent_projection(manager.states[trend_id])
        self.assertEqual(2, effective.evidence_counts["research"])
        self.assertEqual(3, effective.observation_count)
        self.assertEqual(3, effective.actor_diversity)


if __name__ == "__main__":
    unittest.main()
