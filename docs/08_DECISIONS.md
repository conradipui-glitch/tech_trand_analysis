# Decisions

## ADR-001 — GitHub is Project Truth
**Status:** Accepted

GitHub хранит актуальное структурированное состояние проекта. Чат является рабочим интерфейсом. Google Drive хранит тяжёлые первичные материалы и evidence.

## ADR-002 — Source-agnostic Observation schema
**Status:** Accepted

Все provider-specific adapters преобразуют вход в универсальный Observation. Analytics layer не знает конкретные provider names.

## ADR-003 — Minimal high-signal discovery sources
**Status:** Accepted for MVP hypothesis

Не начинать с сотен сайтов и полного научного корпуса. Discovery предпочитает evidence реальной технологической активности: patents, GitHub, Hugging Face Hub для AI.

## ADR-004 — OpenAlex as validation/history layer
**Status:** Accepted for MVP hypothesis

OpenAlex используется преимущественно для first seen, publication dynamics и diversity, а не как единственный генератор трендов.

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
