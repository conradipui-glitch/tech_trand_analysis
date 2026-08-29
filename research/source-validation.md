# Source Validation

**Status:** COMPLETE FOR ARCHITECTURAL DECISION — EPO live-auth smoke test remains as an implementation task.

**Checked:** 2026-08-29

## Goal

Проверить минимальный набор high-signal sources для MVP и понять, можно ли строить один универсальный collector для произвольного технологического направления.

## Main finding

Один фиксированный набор источников с одинаковыми весами использовать нельзя.

Нужен **Source Router**: пользовательское направление классифицируется по типу технологии, после чего включаются релевантные providers и их веса.

Примеры:

| Technology profile | Primary discovery | Validation / history | Low/disabled |
|---|---|---|---|
| AI / software | GitHub + Hugging Face Hub | OpenAlex; EPO as confirmation | — |
| Hardware / semiconductors | EPO + OpenAlex | GitHub when implementation is open-source | HF usually off |
| Materials / energy | EPO + OpenAlex | reports / companies later | GitHub low, HF off |
| AI hardware / neuromorphic | GitHub + EPO + OpenAlex | HF when models/datasets exist | — |

This is still a four-provider MVP. The analytical pipeline remains source-agnostic; only routing and evidence weights change.

---

## 1. GitHub

### Verdict

**MVP: YES, conditional primary source for software-heavy technologies.**

### Access / cost

Public REST API. Authenticated REST requests have a large general quota; repository search has a separate limit of 30 authenticated search requests/minute. GitHub Search returns at most 1,000 results per query, so broad queries must be split by date/topic when necessary.

Official docs:
- https://docs.github.com/en/rest/search/search
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories

### Useful discovery capabilities

Repository search supports qualifiers including:
- `created:` — repository creation date;
- `pushed:` — latest push date;
- `stars:`;
- language/topic/text constraints.

After discovery, repository metadata gives fields useful for evidence scoring:
- `created_at`;
- `updated_at` / `pushed_at`;
- `stargazers_count`;
- `forks_count`;
- owner type / organization;
- language;
- license;
- archive/template/fork status;
- releases/contributors can be fetched only for shortlisted repos.

### Live sanity checks

Queries were tested against current public GitHub data.

`"AI agent" created:>2026-01-01 stars:>20` returned a mixture of strong implementation signals and noise. Relevant examples included `vercel-labs/agent-browser` and `karpathy/autoresearch`, but the same result set also contained tutorial/awesome/marketing-style repositories.

`"neuromorphic" created:>2026-01-01` returned a small but plausible implementation/research-tooling set, including neuromorphic-specific organizations/projects.

`"solid state battery" created:>2025-01-01 stars:>5` returned only a few mostly research/ML repositories. This demonstrates that GitHub cannot be a universal primary source outside software-heavy domains.

A metadata read of `vercel-labs/agent-browser` confirmed that a single discovered repository can expose creation/push dates, organization owner, stars, forks and other activity metrics without downloading code.

### Incremental strategy

Do not crawl GitHub globally.

For each active technology query/profile:
1. expand query into a bounded search vocabulary;
2. search a rolling creation window (`created:>=...`);
3. optionally search `pushed:` for already-known repos;
4. upsert by repository ID;
5. enrich only shortlisted repos;
6. snapshot activity metrics for velocity.

### Noise / required filters

High noise risk. Cheap filters before embeddings:
- exclude forks/templates where appropriate;
- down-rank `awesome-*`, tutorials, course/homework, list collections;
- minimum activity threshold;
- separate organization vs individual owner;
- collapse mirrors / near-duplicate repos;
- distinguish a real product/library from demo code;
- snapshot stars/forks/releases rather than treating absolute stars as trend evidence.

### Complexity

Low–medium.

---

## 2. Hugging Face Hub

### Verdict

**MVP: YES for AI-related directions only. Disabled by Source Router for most non-AI domains.**

### Access / cost

Public Hub API with official Python/JS SDKs.

Official docs:
- https://huggingface.co/docs/hub/api
- https://huggingface.co/docs/huggingface_hub/guides/search
- https://huggingface.co/docs/hub/rate-limits
- https://huggingface.co/docs/hub/webhooks

The free-user Hub API rate limit is currently documented around a 5-minute window and is ample for an incremental MVP; rate limits are explicitly subject to change, so collector must read rate-limit headers / handle 429.

### Useful signals

Separate streams:
- models;
- datasets;
- Spaces.

`ModelInfo` / listing APIs expose fields such as:
- `created_at`;
- `last_modified`;
- downloads (recent / all-time where available);
- likes;
- tags;
- pipeline/library information;
- model relationships / metadata where available.

The CLI/API can sort by `created_at`, downloads, last modified, likes and trending score.

### Incremental strategy

For broad discovery, polling is preferable to webhooks:
1. list newest models/datasets/Spaces ordered by creation time;
2. paginate until `created_at <= checkpoint`;
3. persist only metadata/normalized evidence;
4. periodically refresh metrics for candidate entities.

HF Webhooks are useful for watching known repositories, users or organizations, but are not the primary mechanism for discovering every new repository on the Hub.

### Why the signal is useful

For AI, Hub activity is closer to implementation than papers: a model, dataset or working Space exists as an artifact. Current public Hub pages visibly contain newly created agent environments, evaluation leaderboards, edge/on-device agents and other concrete artifacts.

### Main noise problem

A raw count of Hub repositories is dangerous because one underlying innovation can create hundreds of derivative artifacts:
- quantizations;
- LoRAs;
- conversions;
- mirrors/reuploads;
- fine-tunes;
- demo Spaces around the same model.

Therefore the HF adapter must extract and normalize **model family / base model / artifact role**, then collapse derivatives into one technology-family signal where possible.

### Complexity

Low.

---

## 3. OpenAlex

### Verdict

**MVP: YES. Primary discovery/history source for research-heavy domains; quantitative/history validator for software-heavy domains.**

### Access / cost

REST API over works, authors, institutions, topics and related entities.

Official docs:
- https://help.openalex.org/api/
- https://help.openalex.org/api/filtering/
- https://help.openalex.org/api/grouping/
- https://help.openalex.org/how-to/api-recipes/
- https://help.openalex.org/access/pricing/

Current pricing model provides a free daily API budget. List/filter calls are much cheaper than text/semantic search, so the production design should resolve a user direction to stable topic IDs and then use filters/grouping whenever possible.

### Useful capabilities

- filter by publication date/year;
- search title/abstract metadata;
- OpenAlex Topics and hierarchy;
- `group_by=publication_year` and other dimensions;
- works/authors/institutions/countries/citations;
- select only needed fields.

This makes OpenAlex particularly valuable for:
- publication trajectory;
- institution/actor diversity;
- geographic diffusion;
- historical baseline;
- representative papers.

### Important limitation for our incremental design

True sync filters based on OpenAlex record `created/updated` dates are currently a paid feature.

Therefore the free MVP should **not** rely on `from_updated_date`.

Free incremental approach:
1. keep a rolling publication-date lookback (for example 14–30 days);
2. re-query that window;
3. upsert by OpenAlex work ID;
4. this tolerates late indexing better than querying only “today”;
5. use targeted historical `group_by` queries only after a candidate appears.

### Cost-efficient query pattern

Preferred flow:
1. user direction → query expansion;
2. resolve likely OpenAlex Topics using a small number of search calls;
3. retrieve/count works via topic/date filters;
4. group by year/institution/country as needed;
5. only fetch representative works for evidence.

Do not download the OpenAlex snapshot for MVP.

### Methodology warning

Do not use OpenAlex Topic `created_date` as the trend's `first_seen`: it is the taxonomy object's lifecycle, not necessarily the first appearance of the technology. `first_seen` must come from our semantic/evidence history.

### Complexity

Low.

---

## 4. Patents — EPO Open Patent Services (OPS)

### Verdict

**MVP: YES. Primary for hardware/materials/energy/biotech; high-confidence confirmation for fast software/AI trends.**

### Access / cost

EPO OPS is a REST/XML service backed by the same bibliographic / worldwide legal / full-text databases used by EPO patent products.

Official docs:
- https://www.epo.org/en/searching-for-patents/data/web-services/ops
- https://developers.epo.org/
- https://www.epo.org/en/service-support/faq/searching-patents/open-patent-services/general-information/are-there-any

Registration and OAuth credentials are required.

Non-paying usage currently allows up to 4 GB/week. EPO fair-use guidance describes roughly ten searches/minute/IP as a general rule, stricter limits for some family actions, and limited robot throughput.

### Useful capabilities

- worldwide bibliographic patent data;
- CPC/IPC classification;
- applicants/inventors;
- publication dates;
- families;
- legal events;
- title/abstract/full text depending operation;
- CQL bibliographic search.

### Incremental strategy

Do not bulk-download the patent world.

For each technology profile:
1. map query to CPC/IPC + bounded keyword set;
2. query a rolling publication-date window;
3. request publication references first;
4. enrich bibliographic details only for candidates;
5. aggregate counts by applicant / CPC / period;
6. maintain patent-family deduplication.

### Important interpretation constraint

Patents are high-intent evidence but often **lag the actual invention** because publication occurs after filing/priority. Therefore a patent should increase confidence that a technology is becoming applied, but absence of patents must not suppress a very young software/AI trend.

### Current unresolved implementation item

Documentation/capability is validated, but a real authenticated OPS request has not yet been executed because project EPO developer credentials are not configured.

Create a separate smoke-test task before implementing the production adapter.

### Alternative considered

Google Patents / public patent BigQuery data can be useful for manual validation or a later analytical backend, but using BigQuery introduces another cloud dependency. EPO OPS is a cleaner first production adapter for a Cloudflare/local-first MVP.

### Complexity

Medium, mainly due to OAuth, XML/CQL and patent-family normalization.

---

## Final MVP source decision

Keep exactly four provider families for Phase 1:

1. **GitHub** — implementation evidence for software-heavy domains.
2. **Hugging Face Hub** — AI artifacts only.
3. **OpenAlex** — research discovery + historical/quantitative validation depending domain.
4. **EPO OPS** — patent/application evidence; especially important outside pure software.

Do **not** add news, jobs, startup databases or mass report crawling before end-to-end validation.

## New architectural requirement: Source Router

Before collection, classify the user direction into one or more profiles:

- `software_ai`
- `hardware_semiconductor`
- `materials_energy`
- `bio_medtech`
- `mixed`

The router returns:
- enabled providers;
- provider weights;
- query-expansion strategy;
- evidence-type expectations.

This is configuration, not provider-specific logic in the analytics core.

## Recommended next implementation order

1. OpenAlex adapter — easiest structured historical data and useful for every profile.
2. GitHub adapter — strongest live implementation signal for the initial AI test direction.
3. Hugging Face adapter — easy and highly valuable for AI.
4. EPO OPS smoke test + adapter — after credentials are configured.

## Source spike completion criteria

- provider set selected: **done**;
- conditional applicability identified: **done**;
- incremental collection strategy: **done**;
- cost/rate-limit risks identified: **done**;
- live GitHub sanity check: **done**;
- HF/OpenAlex public API capability verified from official docs/public data: **done**;
- EPO authenticated smoke call: **pending implementation task, not blocking architecture decision**.
