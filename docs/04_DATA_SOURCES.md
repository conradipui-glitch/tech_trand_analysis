# Data Sources

## Принцип выбора

MVP использует минимальное число источников с высоким отношением signal/noise. Предпочтение источникам, где видно реальное действие вокруг технологии: разработка, патентование, создание моделей/репозиториев, переход research → implementation.

## Source Router

Один фиксированный набор источников с одинаковыми весами не подходит для произвольного технологического направления.

Перед сбором направление классифицируется в один или несколько профилей:

- `software_ai`
- `hardware_semiconductor`
- `materials_energy`
- `bio_medtech`
- `mixed`

Router возвращает:
- enabled providers;
- provider weights;
- query-expansion strategy;
- expected evidence types.

Пример:

| Profile | Primary discovery | Validation/history | Обычно отключено/понижено |
|---|---|---|---|
| software_ai | GitHub + Hugging Face | OpenAlex + EPO confirmation | — |
| hardware_semiconductor | EPO + OpenAlex | GitHub conditional | HF |
| materials_energy | EPO + OpenAlex | reports later | GitHub low, HF |
| mixed / AI hardware | GitHub + EPO + OpenAlex | HF conditional | — |

Source routing является конфигурацией и не меняет analytics core.

## MVP provider families

### 1. EPO Open Patent Services

Роль: `patent`.

Ценность:
- есть applicant/inventor;
- CPC/IPC;
- publication/legal/family data;
- высокое намерение превратить идею в защищаемую технологию.

Использование:
- primary discovery для hardware/materials/energy/biotech;
- high-confidence confirmation для software/AI.

Incremental:
- rolling publication-date window;
- CPC/IPC + bounded keyword query;
- сначала publication references, затем enrichment;
- family-level dedup.

Ограничение: патентная публикация запаздывает относительно момента изобретения, поэтому отсутствие patent evidence не является отрицательным сигналом для совсем молодого тренда.

Технически требуется EPO Developer Portal / OAuth. Live authenticated smoke test вынесен в отдельную задачу.

### 2. GitHub

Роль: `implementation`.

Поля:
- repository ID / name / description;
- created_at / pushed_at;
- owner / organization;
- stars / forks;
- language / license;
- activity metrics;
- releases/contributors только для shortlist.

Особенно релевантен software-heavy направлениям.

Incremental:
- bounded query expansion;
- search by rolling `created:` windows;
- `pushed:` refresh для известных repos;
- upsert by repository ID;
- activity snapshots.

Required noise filters:
- forks/templates;
- tutorial/course/homework;
- `awesome-*` / list collections;
- mirrors / near duplicates;
- low-activity demo repositories;
- separate real library/product from educational artifact.

GitHub не является универсальным источником: для materials/energy его вес должен быть низким.

### 3. Hugging Face Hub

Роль: `implementation`, `model`, `dataset`, `space`.

Используется только для AI-related направлений.

Полезные поля:
- created_at;
- last_modified;
- downloads;
- likes;
- tags / pipeline / library;
- base-model/model-family metadata где доступно.

Incremental:
- poll newest models/datasets/Spaces ordered by creation time;
- stop pagination at checkpoint;
- refresh metrics only for candidates.

Критически важно collapse derivatives:
- quantizations;
- LoRA/fine-tunes;
- conversions;
- mirrors/reuploads;
- demo Spaces around the same underlying model.

Иначе один технологический феномен будет ошибочно выглядеть как сотни независимых сигналов.

### 4. OpenAlex

Роль зависит от Source Router.

Для research-heavy профилей:
- discovery + history.

Для software-heavy профилей:
- validation/history.

Полезно для:
- first-seen evidence proxy;
- publication counts;
- author/institution diversity;
- country diversity;
- citation dynamics;
- representative papers;
- historical baseline.

Preferred low-cost flow:
1. user direction → query expansion;
2. resolve likely OpenAlex Topics;
3. use topic/date filters rather than repeated full-text searches;
4. `group_by` for historical counts;
5. fetch representative works only when needed.

Free incremental limitation:
true `from_updated_date` sync is not assumed available in free MVP.

Therefore use:
- rolling publication-date lookback (for example 14–30 days);
- repeated query + upsert by OpenAlex ID;
- targeted historical aggregation after a candidate appears.

Do not use OpenAlex Topic `created_date` as trend `first_seen`.

## Enrichment layer — later/on demand

После обнаружения кандидата:
- аналитические отчёты;
- research labs;
- сайты компаний;
- открытые технологические материалы;
- дополнительные первоисточники.

Reports enrich/validate trends; they should not be the primary source of the TOP-15.

## Что сознательно не входит в initial MVP ingestion

- массовые news feeds;
- вакансии;
- startup databases;
- сотни corporate sites;
- полный OpenAlex snapshot;
- полный patent corpus.

## Расширение

Новый provider добавляется через adapter → `Observation`.

Analytics pipeline не меняется. При добавлении источника меняются только:
- adapter;
- source registry;
- Source Router applicability/weight;
- provider-specific quality rules.
