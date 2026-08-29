# Emerging Trend Methodology

## Основной принцип

`Popularity != Emergence`.

Зрелая популярная технология не должна занимать верх TOP-15 только из-за большого абсолютного числа упоминаний.

## Признаки emerging trend

### Recency / First Seen
Первый устойчивый семантический кластер, а не первое случайное совпадение термина.

В Score v0:
- `first_seen` влияет на novelty proxy;
- `last_seen` влияет на recency / freshness.

### Growth
Рост evidence за период. Score v0 сравнивает среднее последних трёх месяцев с предыдущими тремя через сглаженный log-ratio.

### Acceleration
Изменение нормализованной скорости появления evidence: recent velocity сравнивается с previous velocity.

### Novelty
Целевая методология должна учитывать семантическую дистанцию от зрелых кластеров.

**Score v0 пока использует temporal novelty proxy** — возраст от `first_seen`. Это осознанное упрощение до retrospective calibration и появления достаточно большого cross-trend corpus. Называть этот proxy полноценной semantic novelty нельзя.

### Evidence Diversity
Технология проявляется в нескольких независимых типах evidence.

Evidence semantics зависят от source profile:
- software/AI не обязан иметь patent evidence, если есть research → implementation / adoption;
- hardware/materials/bio получают больший вес за patent/IP слой;
- research → applied transition даёт дополнительный сигнал.

### Actor Diversity
Растёт число независимых организаций / авторов / applicants / developers. В v0 используется логарифмическая насыщаемая функция, чтобы большие зрелые темы не выигрывали только абсолютным масштабом.

### Persistence
Сигнал не является единичным всплеском. Учитываются доля активных месяцев и последовательная серия активных периодов.

### Maturity Penalty
Слишком зрелые темы получают отдельный subtractive penalty. В v0 он активируется после 36 месяцев и учитывает возраст, accumulated observation volume и наличие market/adoption evidence.

## Evidence transition

Особенно важен переход:

```text
Research → Patent → Implementation → Product / Adoption
```

Для MVP движение от research к patent/implementation повышает уверенность, что перед нами технологический, а не только дискурсивный тренд. Для software patent не является обязательной ступенью.

## Emerging Score v0 — provisional weights

Положительная часть суммы:
- Growth: **22%**
- Acceleration: **18%**
- Novelty proxy: **18%**
- Evidence diversity: **14%**
- Actor diversity: **10%**
- Recency: **8%**
- Persistence: **10%**

Сумма положительных весов = 100%.

`Maturity penalty` вычитается отдельно, максимум **30 score points**.

Эти веса — **не финальная методология**. Их задача — дать воспроизводимый baseline для Phase 10 retrospective validation. Изменять веса после B-030 можно только с сохранением benchmark/validation evidence.

## Sparse-history shrinkage

Очень молодой кластер может математически показать огромный growth просто потому, что предыдущий период был нулевым.

Поэтому growth / acceleration / persistence имеют reliability factor. При короткой истории raw component shrink-ится к консервативному prior=25. По мере накопления активных периодов shrink исчезает.

Это защищает от кейса:

```text
0 → 0 → 0 → 0 → 0 → 20 research papers
```

который не должен автоматически считаться полноценным emerging trend.

## Score != Confidence

`score` отвечает на вопрос: **насколько форма сигнала похожа на emerging technology?**

`confidence` отвечает на вопрос: **насколько достаточно evidence, чтобы этому score доверять?**

Confidence v0 учитывает:
- число сохранённых observations;
- provider diversity;
- evidence-type diversity;
- temporal coverage;
- reliability growth/acceleration/persistence.

Молодой качественный сигнал может иметь высокий score и умеренный confidence. Это допустимо и должно быть видно пользователю.

## Stage v0

Рабочие стадии:
- `weak_signal`;
- `emerging`;
- `early_adoption`;
- `unknown`.

Stage не заменяет численный score/confidence и также подлежит retrospective calibration.

## Прозрачность

Для каждого TOP-15 пользователь должен видеть:
- first seen;
- counts / trajectory по периодам;
- growth;
- acceleration;
- novelty proxy;
- evidence composition;
- actor diversity;
- persistence;
- maturity penalty;
- score + confidence;
- representative sources;
- краткое объяснение попадания в TOP.
