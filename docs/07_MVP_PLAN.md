# MVP Plan

## Phase 0 — контракт результата

`technology direction → TOP-15 + evidence + methodology`.

Готово, когда JSON-схема результата согласована.

## Phase 1 — research spike по источникам

Проверить на реальных запросах:
- patents;
- GitHub;
- Hugging Face Hub для AI;
- OpenAlex для history/validation.

Для каждого: доступ, rate limits, поля, incremental retrieval, историческая доступность, signal/noise.

## Phase 2 — Observation contract

Реализовать общую schema и validator. Все MVP adapters должны возвращать одинаковый `Observation`.

## Phase 3 — collectors + checkpoints

Для каждого provider:
- получить только новое;
- сохранить temporary raw;
- сформировать Observation;
- checkpoint;
- retries/logging.

## Phase 4 — cleanup / dedup

- exact IDs;
- canonical URLs;
- hashes;
- fuzzy near-duplicate detection.

## Phase 5 — embedding benchmark

Сравнить минимум 2 кандидата на реальном corpus по topic relevance, duplicate separation, cluster quality, скорости и RAM.

## Phase 6 — clustering

Построить semantic microclusters.

## Phase 7 — TrendState

Новый Observation либо присоединяется к существующему cluster, либо образует candidate microcluster.

## Phase 8 — targeted history

Для новых кандидатов запросить историческую динамику через OpenAlex и patent counts. Не скачивать полный исторический corpus без необходимости.

## Phase 9 — Emerging Trend Score

Реализовать first seen, growth, acceleration, novelty, evidence diversity, actor diversity, persistence и maturity penalty.

## Phase 10 — retrospective validation

Проверить несколько известных трендов прошлого: смогла бы система заметить их раньше широкой очевидности?

## Phase 11 — TOP-15 JSON

До UI получить стабильный machine-readable результат.

## Phase 12 — enrichment

Для finalist candidates найти cases, companies/labs, reports и representative sources.

## Phase 13 — LLM synthesis

LLM нормализует название, пишет объяснение, мотивацию, проблему/преимущество и структурирует case. LLM не выбирает TOP-15 с нуля.

## Phase 14 — API

FastAPI или эквивалент.

## Phase 15 — UI

Поле направления → TOP-15 → карточка trend → methodology/evidence.

## Phase 16 — расширение sources

Только после end-to-end MVP.
