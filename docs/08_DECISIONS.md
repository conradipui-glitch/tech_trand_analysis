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
**Status:** Accepted for spike

Cloudflare рассматривается как основной кандидат для публичного runtime MVP: Workers для API/cron/orchestration, D1 для компактного operational state, R2 для raw/Parquet/evidence, Queues/Workflows для фоновой обработки, Vectorize как возможный managed ANN layer и Workers AI как дополнительный inference provider.

Это не отменяет local-first ML: тяжёлые embeddings/clustering/эксперименты могут выполняться локально или на VPS, а Cloudflare обслуживает публичный сервис и лёгкую оркестрацию. Перед фиксацией production architecture провести отдельный deployment/cost spike.

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
