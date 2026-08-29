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
- добавлена отдельная задача authenticated EPO OPS smoke test.

### Changed
- отказ от идеи собирать полный научно-технологический интернет;
- роль OpenAlex уточнена: discovery+history для research-heavy domains, validation/history для software-heavy domains;
- discovery MVP смещён к evidence реального технологического действия;
- аналитические отчёты переведены преимущественно в enrichment/validation;
- отказ от сотен custom parsers как базовой архитектуры;
- GitHub и Hugging Face больше не считаются универсальными источниками: их вес зависит от source profile;
- patent evidence признан сильным, но запаздывающим сигналом и не используется как обязательный gate для молодых software trends.

### Current focus
Observation contract + output JSON contract + Cloudflare runtime spike.
