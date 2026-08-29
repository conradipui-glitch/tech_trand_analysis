# Changelog

## 2026-08-29

### Added
- сформулирован буквальный контракт сервиса;
- зафиксирована source-agnostic Observation architecture;
- определена стратегия incremental collection;
- определена идея targeted historical backfill;
- выделен Emerging Trend Engine;
- сформирован local-first ML подход;
- создан initial MVP plan;
- GitHub назначен основным source of truth проекта;
- Google Drive назначен архивом тяжёлых материалов и evidence;
- завершён source validation spike по GitHub, Hugging Face Hub, OpenAlex и EPO OPS;
- добавлен Source Router по типу технологического направления;
- добавлена отдельная задача authenticated EPO OPS smoke test;
- зафиксированы `Observation` и TOP-15 JSON contracts v0.2.0 с fixtures/contract tests;
- реализован первый production-shaped adapter: OpenAlex;
- добавлены Memory/File checkpoint stores и локальный JSONL.gz raw sink с R2-compatible layout;
- добавлен generic resumable `CollectionRunner` с raw-before-checkpoint commit order;
- собрана первая вертикаль OpenAlex → raw → Observation → checkpoint;
- добавлен GitHub Actions CI; contract/adapter/router/storage/collection tests проходят успешно.

### Changed
- отказ от идеи собирать полный научно-технологический интернет;
- роль OpenAlex уточнена: discovery+history для research-heavy domains, validation/history для software-heavy domains;
- discovery MVP смещён к evidence реального технологического действия;
- аналитические отчёты переведены преимущественно в enrichment/validation;
- отказ от сотен custom parsers как базовой архитектуры;
- GitHub и Hugging Face больше не считаются универсальными источниками: их вес зависит от source profile;
- patent evidence признан сильным, но запаздывающим сигналом и не используется как обязательный gate для молодых software trends;
- provider и artifact kind больше не зашиты закрытыми enum-списками в центральный контракт: расширение providers не требует пересборки analytics schema;
- Cloudflare принят как hybrid runtime, а не место для всей тяжёлой ML-обработки.

### Current focus
B-013 exact/fuzzy dedup → evaluation corpus → embedding benchmark → clustering.
