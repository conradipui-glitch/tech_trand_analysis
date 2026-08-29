# Embedding Benchmark

**Status:** NOT STARTED

## Goal

Выбрать embedding model для local-first MVP на собственном technological corpus.

## Initial candidates

- Qwen3-Embedding-0.6B
- BGE-M3

## Test tasks

1. Exact-topic retrieval.
2. Near-duplicate discrimination.
3. Similar technology grouping.
4. Separation of adjacent but distinct technologies.
5. Russian ↔ English semantic alignment.
6. Runtime / RAM.
7. Embedding storage size.

## Decision rule

Выбирать модель по качеству на нашем corpus и operating cost, а не только по публичным leaderboard.
