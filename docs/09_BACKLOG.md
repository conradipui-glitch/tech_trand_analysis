# Backlog

## NOW

- [ ] B-001 Провести source validation spike: patent source.
- [ ] B-002 Провести source validation spike: GitHub.
- [ ] B-003 Провести source validation spike: Hugging Face Hub.
- [ ] B-004 Провести source validation spike: OpenAlex historical/quantitative queries.
- [ ] B-005 Уточнить и зафиксировать Observation schema.
- [ ] B-006 Зафиксировать JSON contract итоговой карточки тренда.
- [ ] B-007 Провести Cloudflare deployment/cost spike: Workers, D1, R2, Queues/Workflows, Vectorize, Workers AI; определить границу Cloudflare vs local/VPS.

## NEXT

- [ ] B-010 Реализовать первый adapter.
- [ ] B-011 Реализовать incremental checkpoints.
- [ ] B-012 Реализовать raw buffer.
- [ ] B-013 Реализовать exact/fuzzy dedup.
- [ ] B-014 Собрать evaluation corpus.
- [ ] B-015 Benchmark embeddings.
- [ ] B-016 Prototype clustering.
- [ ] B-017 TrendState prototype.
- [ ] B-018 Targeted historical backfill.
- [ ] B-019 Emerging Score v0.

## VALIDATION

- [ ] B-030 Retrospective test на нескольких известных emerging technologies.
- [ ] B-031 Проверить false positive: research-only cluster.
- [ ] B-032 Проверить transition research → patent → implementation.

## LATER

- [ ] B-008 После проверки возможностей Cloudflare, первого deployment и стартовых тестов отозвать/перевыпустить временные Cloudflare API/R2 credentials, использованные при настройке. Новые credentials хранить только в Cloudflare Secrets/secret manager, не в чате и не в GitHub.
- [ ] B-050 Targeted report enrichment.
- [ ] B-051 Company/research case enrichment.
- [ ] B-052 API/runtime deployment после результата Cloudflare spike.
- [ ] B-053 UI.
- [ ] B-054 Дополнительные providers.
- [ ] B-055 Dataset для distillation.

## BLOCKED

Нет текущих blockers.
