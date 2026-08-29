# Backlog

## NOW

- [x] B-001 Провести source validation spike: patent source. Выбран EPO OPS; capability validated, authenticated smoke вынесен в B-009.
- [x] B-002 Провести source validation spike: GitHub.
- [x] B-003 Провести source validation spike: Hugging Face Hub.
- [x] B-004 Провести source validation spike: OpenAlex historical/quantitative queries.
- [x] B-005 Уточнить и зафиксировать Observation schema с учётом Source Router и provider-specific metrics. Закрыто schema v0.2.0 + fixtures + contract tests.
- [x] B-006 Зафиксировать JSON contract итоговой карточки тренда. Закрыто `trend-result.schema.json` v0.2.0 + fixture.
- [x] B-007 Провести Cloudflare capability/cost spike: Workers, D1, R2, Queues/Workflows, Vectorize, Workers AI, AI Gateway. Принят hybrid runtime ADR-014; live smoke вынесен в B-021.
- [x] B-010 Реализовать первый adapter: OpenAlex. Есть retry/cursor pagination/mapping в Observation v0.2.0 + tests.
- [x] B-011 Реализовать incremental checkpoints. Есть Memory/File stores + atomic local persistence + tests.
- [x] B-012 Реализовать raw buffer. Есть JSONL.gz sink с R2-compatible key layout + tests.
- [x] B-013 Реализовать exact/fuzzy dedup. Exact DOI/URL/provider IDs + conservative title fuzzy; research/implementation evidence не схлопываются; tests green.
- [x] B-014 Собрать evaluation corpus. v0: 48 passages / 12 clusters / 3 profiles / RU+EN, 24 retrieval queries, 24 pair cases, explicit hard negatives; corpus validation green in CI.
- [x] B-015 Benchmark embeddings. Реальные CPU GitHub Actions runs: BGE-M3 выбран primary для clustering; Qwen3-Embedding-0.6B оставлен retrieval/fallback candidate. Raw results persisted in `research/benchmark-results/`.
- [x] B-016 Prototype clustering на BGE-M3 geometry. Выбран profile-aware conservative microclustering без заранее известного числа кластеров; software=hybrid dense+TF-IDF, hardware=cosine agglomerative, materials=purity-first conservative split. Benchmark + production tests green.
- [x] B-020 Реализовать Source Router v0 (`software_ai`, `hardware_semiconductor`, `materials_energy`, `bio_medtech`, `mixed`) + routing tests.
- [x] B-022 Собрать resumable collection vertical slice: OpenAlex → raw → Observation → checkpoint. Проверено interruption/resume и GitHub Actions CI.
- [x] B-023 Реализовать durable normalized ObservationStore между dedup и embeddings. Есть Memory + SQLite реализации, upsert/filter contract и CI tests; SQLite schema intentionally D1-friendly.
- [ ] B-017 TrendState prototype: long-lived trend identity, centroid matching/merge, evidence/provider/actor diversity, first_seen/last_seen и period buckets.

## NEXT

- [ ] B-009 Получить/настроить EPO OPS developer credentials и выполнить authenticated smoke query; секреты не коммитить.
- [ ] B-018 Targeted historical backfill.
- [ ] B-019 Emerging Score v0.
- [ ] B-021 Live Cloudflare smoke: Worker + D1 + R2 + Workers AI; проверить bindings/deploy, простой end-to-end request и записать результат. После успешного smoke выполнить B-008.

## VALIDATION

- [ ] B-030 Retrospective test на нескольких известных emerging technologies.
- [ ] B-031 Проверить false positive: research-only cluster.
- [ ] B-032 Проверить transition research → patent → implementation.
- [ ] B-033 Проверить profile routing на минимум трёх направлениях: AI agents, neuromorphic computing, solid-state batteries.

## LATER

- [ ] B-008 После проверки возможностей Cloudflare, первого deployment и стартовых тестов отозвать/перевыпустить временные Cloudflare API/R2 credentials, использованные при настройке. Новые credentials хранить только в Cloudflare Secrets/secret manager, не в чате и не в GitHub.
- [ ] B-050 Targeted report enrichment.
- [ ] B-051 Company/research case enrichment.
- [ ] B-052 Полный API/runtime deployment после detector vertical slice.
- [ ] B-053 UI.
- [ ] B-054 Дополнительные providers.
- [ ] B-055 Dataset для distillation.
- [ ] B-056 Оценить R2 Data Catalog/R2 SQL после появления реального Parquet/Iceberg workload.

## BLOCKED

- B-021 live Cloudflare smoke требует доступного Cloudflare action/tool или запуска Wrangler/API из среды с внешней сетью.
- B-009 EPO live smoke требует отдельной EPO OPS регистрации/credentials.

Текущий core pipeline не заблокирован: B-017 TrendState строится поверх уже выбранного BGE-M3 + profile-aware microclustering.
