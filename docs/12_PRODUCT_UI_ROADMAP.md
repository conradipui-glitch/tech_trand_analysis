# Product UI roadmap — after detector quality gates

Status: **future product design brief**. No UI redesign authorized or required during B-043, B-036, B-037 validation. Keep the existing Cloudflare operator shell usable and truthful until arbitrary-direction analysis produces grounded candidates.

## Product's primary workflow

A specialist enters a technological direction → sees collecting / calculating / not enough evidence status → receives ranked emerging-trend candidates with confidence and freshness → opens one candidate and inspects transparent evidence, source links, history and uncertainty → exports a reproducible report.

This is **an analytical application**, not a marketing landing page. Maximize workspace for readable data and comparison, not a decorative hero. An empty TOP-15 must remain partial/insufficient rather than be padded by DeepSeek. Narrative guidance is downstream, derived from grounded results, explicitly labelled as analytical interpretation rather than observed evidence.

## Planned information architecture

1. **Analysis workspace** — direction query, profile, date range, collection progress, last updated, partial/failure states and reason.
2. **Trend results** — ranked cards/table with emerging score vs confidence *as separate properties*, trend title, technology profile, first verified evidence date, velocity/acceleration, source diversity, peer/actor count with anti-double-count.
3. **Trend detail** — monthly source timeline (research, patent/IP if appropriate, verified implementation), interactive chart, evidence list with direct URLs and timestamp provenance, clustering rationale, limits/conflicts, investigated hypotheses and grounded DeepSeek 'what to monitor next'.
4. **Comparison / export** — side-by-side trends and export of underlying evidence/criteria, JSON/report snapshots and date of run.
5. **Methodology / system** — transparent scoring formula and its version, confidence semantics, current provider health, freshness, validation caveats.

## Design and development method

The user provided the multi-file **Frontend Studio** skill package in this conversation (main skill, copywriting, design system, quality review, SEO/Yandex, sources, web presentations and agent metadata). When B-053 starts, use that user-provided package as the design brief/method and check its contents/version with the user or corresponding uploaded files. Do not automatically publish the user's entire authored skill in this **public** GitHub repository without confirmation.

Selected applicable principles from the skill (adapted to this actual product):
- Preserve existing stack, visual affordances and working shell; only change what improves a user journey.
- Design the workspace from real information architecture and actual loaded observations, then create reusable layout/type/color/interaction tokens.
- Honor RU/Cyrillic, long trend names, responsive layout, keyboard and focus navigation, loading/error/empty/partial states, touch, reduced motion and source provenance.
- Screenshots/visual inspection at desktop and narrow mobile, plus real end-to-end interaction checks and console/network verification. A green CI isn't a visual approval.
- Treat public SEO and marketing copy separately from the **internal analysis workspace**; don't apply SEO mechanics to the dashboard or invent evidence/awards/reviews.

## Timing gate

Start substantive redesign only once dynamic direction → collection → dedup/embeddings/clustering → TrendState → verified history → Emerging Score → TOP candidates works end-to-end with a meaningful reviewed example. Until then, keep B-025 operator shell minimal and allow incremental fixes only if they prevent real testing.

## Explicit non-goals for now

No design framework migration, no 3D/animations for appearance alone, no artificial trend summaries, no extensive content-site SEO, no fake report metrics, and no production exposure of experimental B-043 ancestry evidence.
