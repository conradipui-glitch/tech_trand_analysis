# Data Sources

## Принцип выбора

MVP использует минимальное число источников с высоким отношением signal/noise. Предпочтение источникам, где видно реальное действие вокруг технологии: разработка, патентование, создание моделей/репозиториев, переход research → implementation.

## Discovery layer MVP

### Patents
Роль: `patent`.

Ценность:
- технология требует вложения ресурсов;
- есть applicant/inventor;
- есть классификация;
- можно строить временную динамику.

Кандидаты: EPO; Роспатент при необходимости российского слоя.

### GitHub
Роль: `implementation`.

Поля:
- repository;
- description;
- topics;
- created_at / updated_at;
- stars;
- forks;
- contributors / organization;
- releases/activity при необходимости.

Особенно релевантен software-heavy направлениям.

### Hugging Face Hub
Роль: `implementation` / `model` / `dataset`.

Особенно полезен для AI-направлений и не должен быть обязательным для других технологических областей.

## Validation / historical layer

### OpenAlex
Роль:
- first-seen proxy;
- publication counts;
- author/institution diversity;
- country diversity;
- citation dynamics;
- historical baseline.

OpenAlex не должен единолично генерировать emerging trends.

## Enrichment layer

После обнаружения кандидата:
- аналитические отчёты;
- research labs;
- сайты компаний;
- открытые технологические материалы;
- дополнительные первоисточники.

## Расширение

Новый provider добавляется через adapter → Observation. Аналитический pipeline не меняется.
