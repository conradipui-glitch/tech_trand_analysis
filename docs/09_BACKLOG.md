# Backlog

## NOW

- [x] B-001 Провести source validation spike: patent source. Выбран EPO OPS; capability validated, authenticated smoke вынесен в B-009.
- [x] B-002 Провести source validation spike: GitHub.
- [x] B-003 Провести source validation spike: Hugging Face Hub.
- [x] B-004 Провести source validation spike: OpenAlex historical/quantitative queries.
- [ ] B-005 Уточнить и зафиксировать Observation schema с учётом Source Router и provider-specific metrics.
- [ ] B-006 Зафиксировать JSON contract итоговой карточки тренда.
- [ ] B-007 Провести Cloudflare deployment/cost spike: Workers, D1, R2, Queues/Workflows, Vectorize, Workers AI; определить границу Cloudflare vs local/VPS.

## NEXT

- [ ] B-009 Получить/настроить EPO OPS developer credentials и выполнить authenticated smoke query; секреты не коммитить.
- [ ] B-010 Реализовать первый adapter: OpenAlex.
- [ ] B-011 Реализовать incremental checkpoints.
- [ ] B-012 Реализовать raw buffer.
- [ ] B-013 Реализовать exact/fuzzy dedup.
- [ ] B-014 Собрать evaluation corpus.
- [ ] B-015 Benchmark embeddings.
- [ ] B-016 Prototype clustering.
- [ ] B-017 TrendState prototype.
- [ ] B-018 Targeted historical backfill.
- [ ] B-019 Emerging Score v0.
- [ ] B-020 Реализовать Source Router v0 (`software_ai`, `hardware_semiconductor`, `materials_energy`, `bio_medtech`, `mixed`).

## VALIDATION

- [ ] B-030 Retrospective test на нескольких известных emerging technologies.
- [ ] B-031 Проверить false positive: research-only cluster.
- [ ] B-032 Проверить transition research → patent → implementation.
- [ ] B-033 Проверить profile routing на минимум трёх направлениях: AI agents, neuromorphic computing, solid-state batteries.

## LATER

- [ ] B-008 После проверки возможностей Cloudflare, первого deployment и стартовых тестов отозвать/перевыпустить временные Cloudflare API/R2 credentials, использованные при настройке. Новые credentials хранить только в Cloudflare Secrets/secret manager, не в чате и не в GitHub.
- [ ] B-050 Targeted report enrichment.
- [ ] B-051 Company/research case enrichment.
- [ ] B-052 API/runtime deployment после результата Cloudflare spike.
- [ ] B-053 UI.
- [ ] B-054 Дополнительные providers.
- [ ] B-055 Dataset для distillation.

## BLOCKED

Нет архитектурных blockers. EPO live smoke требует отдельной регистрации/credentials, но не блокирует B-005/B-006/B-007/B-010.
