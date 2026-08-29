# Emerging Trend Methodology

## Основной принцип

`Popularity != Emergence`.

Зрелая популярная технология не должна занимать верх TOP-15 только из-за большого абсолютного числа упоминаний.

## Признаки emerging trend

### Recency / First Seen
Первый устойчивый семантический кластер, а не первое случайное совпадение термина.

### Growth
Рост evidence за период.

### Acceleration
Ускорение темпа появления evidence.

### Novelty
Семантическая дистанция от зрелых кластеров.

### Evidence Diversity
Технология проявляется в нескольких независимых типах evidence.

### Actor Diversity
Растёт число независимых организаций / авторов / applicants / developers.

### Persistence
Сигнал не является единичным всплеском.

### Maturity Penalty
Слишком зрелые темы получают понижение.

## Evidence transition

Особенно важен переход:

```text
Research → Patent → Implementation → Product / Adoption
```

Для MVP движение от research к patent/implementation повышает уверенность, что перед нами технологический, а не только дискурсивный тренд.

## Черновой Emerging Score

Веса требуют экспериментальной калибровки. Стартовая гипотеза:
- Growth: 25%
- Acceleration: 20%
- Novelty: 20%
- Evidence diversity: 15%
- Actor diversity: 10%
- Recency: 10%
- Maturity penalty: отдельный штраф

## Прозрачность

Для каждого TOP-15 пользователь должен видеть first seen, counts по периодам, growth, acceleration, evidence composition, representative sources и краткое объяснение попадания в TOP.
