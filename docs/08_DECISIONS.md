# Decisions

## ADR-001 — GitHub is Project Truth
**Status:** Accepted

GitHub хранит актуальное структурированное состояние проекта. Чат является рабочим интерфейсом. Google Drive хранит тяжёлые первичные материалы и evidence.

## ADR-002 — Source-agnostic Observation schema
**Status:** Accepted

Все provider-specific adapters преобразуют вход в универсальный Observation. Analytics layer не знает конкретные provider names.

## ADR-003 — Minimal high-signal discovery sources
**Status:** Accepted

Не начинать с сотен сайтов и полного научного корпуса. Initial MVP ограничен четырьмя provider families: EPO OPS, GitHub, Hugging Face Hub, OpenAlex.

Приоритет источника зависит от типа технологического направления.

## ADR-004 — OpenAlex has profile-dependent role
**Status:** Accepted

OpenAlex используется как discovery + history source для research-heavy направлений и как quantitative/history validation layer для software-heavy направлений. Он не должен единолично генерировать emerging trends.

## ADR-005 — Reports are enrichment first
**Status:** Accepted

Аналитические отчёты используются главным образом для validation/context/cases после обнаружения тренда.

## ADR-006 — Incremental + targeted backfill
**Status:** Accepted

Постоянно фиксируется новое. Исторический backfill запускается только для интересных candidate clusters.

## ADR-007 — Local-first ML
**Status:** Accepted

Embeddings, reranking, clustering и математика должны иметь путь к локальному исполнению. Strong API LLM используется только в верхнем аналитическом слое.

## ADR-008 — No heavyweight data infrastructure for MVP
**Status:** Accepted

Не использовать Kafka/Spark/Kubernetes/Airflow без реальной необходимости.

## ADR-009 — Prove JSON before UI
**Status:** Accepted

Сначала добиться качественного TOP-15 в JSON с evidence и метриками; затем строить UI.

## ADR-010 — Cloudflare as candidate MVP runtime
**Status:** Superseded by ADR-014 after spike

Cloudflare рассматривался как кандидат публичного runtime. Capability/cost spike завершён и решение уточнено в ADR-014.

Секреты Cloudflare никогда не коммитить и не сохранять в проектной документации; использовать Secrets/Bindings/локальные env-файлы вне Git.

## ADR-011 — Profile-aware Source Router
**Status:** Accepted

До запуска collection пользовательское технологическое направление классифицируется в source profile (`software_ai`, `hardware_semiconductor`, `materials_energy`, `bio_medtech`, `mixed`).

Source Router определяет:
- какие providers включены;
- их веса;
- query-expansion strategy;
- expected evidence types.

Причина: live source spike показал, что GitHub/Hugging Face дают сильный implementation signal для AI/software, но резко теряют покрытие для material/energy domains. Для последних EPO/OpenAlex должны становиться primary.

Это не меняет source-agnostic analytics core; routing хранится в конфигурации.

## ADR-012 — Patent evidence is strong but lagging
**Status:** Accepted

Patent signal повышает confidence в переходе технологии к applied/IP activity, но не является обязательным условием emerging trend. Патентная публикация может заметно запаздывать относительно invention/implementation, особенно для быстро развивающегося software/AI.

Поэтому отсутствие патентов не даёт negative penalty молодым software trends; для hardware/materials patent evidence имеет значительно больший вес.

## ADR-013 — Extensible provider contract, stable evidence semantics
**Status:** Accepted

`Observation.provider`, `artifact_kind`, actor kind и relationship type не являются enum в центральной schema. Новый источник может появиться в `sources.yaml` и adapter layer без изменения аналитического ядра и transport contract.

Напротив, `evidence_type` остаётся небольшой стабильной семантической таксономией, потому что именно она используется в cross-source scoring. Неизвестный provider-specific тип должен быть отображён в существующий evidence class или `other`, а не протаскиваться в scoring как новый произвольный класс.

Итоговая выдача TOP-15 обязана отдельно показывать `score` и `confidence`, coverage источников и все score components. Если evidence недостаточно, сервис возвращает `partial`/`insufficient_evidence`, а не придумывает 15 слабых трендов ради заполнения списка.

## ADR-014 — Cloudflare hybrid runtime v0
**Status:** Accepted for MVP

Capability/cost spike показал, что Cloudflare подходит как основной публичный runtime, но Workers Free не подходит для тяжёлого численного ML из-за 10 ms CPU/request.

Распределение ответственности:

- **Worker + static assets** — API/UI, request validation, status, лёгкая маршрутизация;
- **D1** — jobs, checkpoints, source health, TrendState и компактные агрегаты;
- **R2** — raw/normalized batches, evidence, candidate vectors и exports;
- **Queues** — только batch/page-level jobs, не одна очередь на каждый Observation;
- **Workflows** — network-bound orchestration;
- **Workers AI** — first-class candidate для embeddings/rerank/cheap inference;
- **AI Gateway** — observability, spend/rate limits, retries/fallback и external analyst routing;
- **Vectorize** — trend/microcluster centroids и небольшой active candidate layer, не весь document corpus;
- **local PC/VPS** — heavy clustering, retrospective backfills, model benchmarks и distillation.

Причина Vectorize policy: Free tier хранит 5M vector dimensions, то есть примерно 4.9k 1024-dimensional vectors. Этого достаточно для trend centroids, но недостаточно для большого observation corpus.

Workers AI free allocation при текущем тарифе Qwen3-Embedding-0.6B/BGE-M3 теоретически покрывает около 9.3M embedding input tokens/day, если не расходовать общий дневной neuron pool на другие модели. Поэтому Cloudflare embeddings включаются в benchmark рядом с local providers, но не считаются заранее победителем.

R2 Data Catalog/R2 SQL остаются later-stage опцией: технически полезны для Iceberg/Parquet analytics, но создают лишнюю сложность до доказательства detector core.

## ADR-015 — Durable normalized ObservationStore before embeddings
**Status:** Accepted

Между dedup и embeddings нужен отдельный долговременный слой нормализованных Observation. Иначе checkpoint может продвинуться, raw останется сохранённым, но downstream pipeline будет вынужден каждый раз восстанавливать normalized state из сырого batch.

Для MVP используется стабильный интерфейс `ObservationStore`.

Первая local/VPS реализация — SQLite из стандартной библиотеки:
- `observation_id` как primary key;
- JSON payload сохраняет полный Observation contract;
- отдельные индексируемые поля для provider/evidence/artifact/date/direction/cluster;
- повторный сбор обновляет запись через upsert;
- схема намеренно близка к будущему D1 implementation.

Parquet/DuckDB не добавляются на этом этапе только ради архитектурной симметрии. Они появятся, когда embedding/clustering benchmark даст реальный аналитический corpus и станет ясно, какие columnar queries действительно нужны.
