# ML Stack

## Принцип

Дорогая модель не должна смотреть на весь поток данных.

```text
raw
→ deterministic filters
→ dedup
→ cheap similarity
→ embeddings
→ ANN / clustering
→ statistical anomaly detection
→ reranking / classification
→ strong LLM only for finalists
```

## Local-first candidates

### Embeddings
Кандидаты для benchmark:
- Qwen3-Embedding-0.6B
- BGE-M3

Выбор делать на собственном тестовом корпусе.

### Reranking
Кандидат:
- Qwen3-Reranker-0.6B

### Small local LLM / classifier / extractor
Кандидаты:
- Qwen3.5-0.8B
- Qwen3.5-2B
- альтернативная small model после benchmark

### ANN / clustering
- FAISS
- HDBSCAN
- UMAP при необходимости preprocessing/visualization

### Mathematics / time series
- NumPy / Polars / DuckDB
- robust z-score
- EWMA
- CUSUM
- changepoint detection
- velocity / acceleration
- entropy/diversity metrics

## Provider abstraction

Компоненты должны обращаться к интерфейсам:
- `EmbeddingProvider`
- `RerankerProvider`
- `ExtractorProvider`
- `AnalystProvider`

Это позволяет заменить API на local без переписывания pipeline.

## Distillation path

Сохранять features, решения сильной модели и human correction при наличии. Позже использовать этот dataset для local student.
