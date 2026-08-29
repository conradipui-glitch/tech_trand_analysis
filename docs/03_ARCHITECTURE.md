# Architecture

## Главная схема

```text
Technology Direction
        ↓
Query Understanding / Expansion
        ↓
MVP Discovery Sources
        ↓
Source Adapters
        ↓
Observation
        ↓
Deterministic cleanup
        ↓
Exact / fuzzy dedup
        ↓
Embeddings
        ↓
Semantic clustering / routing
        ↓
Trend Candidate
        ↓
Targeted historical validation
        ↓
Temporal metrics
        ↓
Emerging Trend Score
        ↓
TOP candidates
        ↓
Targeted reports / cases / sources
        ↓
LLM synthesis
        ↓
TOP-15 trend cards
```

## Source isolation

Аналитическое ядро не должно знать о GitHub, OpenAlex, EPO и других конкретных провайдерах. Каждый источник преобразуется adapter-слоем в `Observation`.

## Observation draft

```json
{
  "observation_id": "...",
  "provider": "github",
  "evidence_type": "implementation",
  "external_id": "...",
  "published_at": "...",
  "title": "...",
  "text": "...",
  "url": "...",
  "actors": [],
  "technologies": [],
  "metrics": {},
  "raw_ref": "..."
}
```

## Evidence types

- research
- patent
- implementation
- product
- adoption
- investment
- regulation
- analysis

## Dynamic collection principle

Система фиксирует новое, обнаруживает candidate cluster и только затем запрашивает историю конкретного кандидата. Постоянно хранится compact `TrendState` и representative evidence, а не полный внешний корпус.

## TrendState draft

```json
{
  "trend_id": "...",
  "label": "...",
  "first_seen": "...",
  "updated_at": "...",
  "evidence_counts": {},
  "velocity": 0.0,
  "acceleration": 0.0,
  "novelty": 0.0,
  "source_diversity": 0.0,
  "actor_diversity": 0.0,
  "maturity": 0.0,
  "score": 0.0
}
```

## Storage MVP

Допустимо начать с:
- JSONL.gz для временного raw;
- Parquet для нормализованных данных;
- DuckDB для аналитики;
- FAISS или аналог для ANN;
- позже PostgreSQL для API/UI state.

Kafka, Spark, Airflow, Kubernetes и микросервисы для MVP не нужны.
