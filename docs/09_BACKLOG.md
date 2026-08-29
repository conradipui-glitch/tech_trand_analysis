# Backlog

## NOW

- [x] B-001 Провести source validation spike: patent source. Выбран EPO OPS; capability validated, authenticated smoke вынесен в B-009.
- [x] B-002 Провести source validation spike: GitHub.
- [x] B-003 Провести source validation spike: Hugging Face Hub.
- [x] B-004 Провести source validation spike: OpenAlex historical/quantitative queries.
- [x] B-005 Уточнить и зафиксировать Observation schema с учётом Source Router и provider-specific metrics. Закрыто schema v0.2.0 + fixtures + contract tests.
- [x] B-006 Зафиксировать JSON contract итоговой карточки тренда. Закрыто `trend-result.schema.json` v0.2.0 + fixture.
- [x] B-007 Провести Cloudflare capability/cost spike. Принят hybrid runtime ADR-014.
- [x] B-010 Реализовать первый adapter: OpenAlex. Есть retry/cursor pagination/mapping в Observation v0.2.0 + tests.
- [x] B-011 Реализовать incremental checkpoints. Есть Memory/File stores + atomic local persistence + tests.
- [x] B-012 Реализовать raw buffer. Есть JSONL.gz sink с R2-compatible key layout + tests.
- [x] B-013 Реализовать exact/fuzzy dedup. Exact DOI/URL/provider IDs + conservative title fuzzy; research/implementation evidence не схлопываются; tests green.
- [x] B-014 Собрать evaluation corpus. v0: 48 passages / 12 clusters / 3 profiles / RU+EN, 24 retrieval queries, 24 pair cases, explicit hard negatives; corpus validation green in CI.
- [x] B-015 Benchmark embeddings. BGE-M3 выбран primary для clustering; Qwen3-Embedding-0.6B оставлен retrieval/fallback candidate.
- [x] B-016 Prototype clustering на BGE-M3 geometry. Profile-aware conservative microclustering; benchmark + production tests green.
- [x] B-017 TrendState prototype. Long-lived identity, centroid continuation, idempotent rolling collection, evidence/provider/actor diversity, first_seen/last_seen, monthly buckets; CI green.
- [x] B-018 Adaptive targeted historical backfill. Candidate queries + bounded windows + centroid similarity gate; CI green.
- [x] B-019 Emerging Score v0. Transparent score + confidence, sparse-history shrinkage, profile-aware evidence semantics and maturity penalty; guard tests green. Weights provisional until retrospective calibration.
- [x] B-020 Реализовать Source Router v0 (`software_ai`, `hardware_semiconductor`, `materials_energy`, `bio_medtech`, `mixed`) + routing tests.
- [x] B-022 Собрать resumable collection vertical slice: OpenAlex → raw → Observation → checkpoint.
- [x] B-023 Реализовать durable normalized ObservationStore. Memory + SQLite, D1-friendly schema.
- [x] B-024 TOP-15 ranking + `TrendAnalysisResult` assembler. Deterministic ranking из уже обнаруженных TrendState; максимум 15, без LLM padding; кандидаты без grounded source fail-closed; schema contract tests green.
- [x] B-025 Thin operator web shell на Cloudflare Workers + Static Assets. Live deploy + external public smoke green: HTML, `/api/health`, `/api/current`, RAG/LoRA snapshots.
- [x] B-026 Grounded DeepSeek analyst layer через GitHub Actions secret `DEEPSEEK_API_KEY`. DeepSeek не участвует в discovery/ranking; citations constrained to input; unsupported problem/advantage claims fail-closed; live smoke green.
- [ ] B-030 Retrospective validation/calibration. v0.1 обнаружил methodological failure: broad keyword retrieval давал большие pre-origin counts. v0.2 сохраняет те же preregistered RAG/LoRA origin/milestone/query и пропускает aggregate history через conservative semantic sample gate; live rerun запущен. Production backfill по-прежнему использует настоящий centroid similarity gate.

## NEXT

- [ ] B-027 Подключить vetted DeepSeek narrative к опубликованному TOP-candidate snapshot после assembler; хранить enrichment как производный слой, не как evidence.
- [ ] B-031 Проверить false positive: research-only cluster на retrospective/live evidence.
- [ ] B-032 Проверить transition research → patent → implementation.
- [ ] B-033 Проверить profile routing на минимум трёх направлениях: AI agents, neuromorphic computing, solid-state batteries.
- [ ] B-009 Получить/настроить EPO OPS developer credentials и выполнить authenticated smoke query; секреты не коммитить.
- [ ] B-021 Продолжить Cloudflare live capability smoke: Worker/public shell уже проверены; остаются D1 + R2 + Workers AI bindings и минимальный end-to-end data write/read/inference test. Только после полного smoke выполнить B-008.

## LATER

- [ ] B-008 После полной проверки Cloudflare возможностей, первого deployment и стартовых тестов отозвать/перевыпустить временные Cloudflare API/R2 credentials, использованные при настройке. Новые credentials хранить только в Cloudflare/GitHub Secrets или другом secret manager, не в чате и не в Git.
- [ ] B-050 Targeted report enrichment.
- [ ] B-051 Company/research case enrichment.
- [ ] B-052 Полный API/runtime deployment detector jobs после vertical slice.
- [ ] B-053 Final product UI polish поверх уже работающего operator shell.
- [ ] B-054 Дополнительные providers.
- [ ] B-055 Dataset для distillation.
- [ ] B-056 Оценить R2 Data Catalog/R2 SQL после появления реального Parquet/Iceberg workload.

## BLOCKED

- B-009 EPO live smoke требует отдельной EPO OPS регистрации/credentials.

Текущий detector core и web shell не заблокированы. Cloudflare Worker deployment и публичный smoke работают через GitHub Actions; D1/R2/Workers AI capability smoke остаётся отдельной инфраструктурной задачей.
