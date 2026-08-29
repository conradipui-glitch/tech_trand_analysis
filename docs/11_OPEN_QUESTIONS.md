# Open Questions

## Sources
- Какой patent API/источник оптимален для MVP по доступности и качеству?
- Насколько GitHub Search/API позволяет стабильно строить incremental technology discovery?
- Какие Hugging Face Hub signals лучше всего отражают emergence?
- Какой минимальный набор OpenAlex запросов даёт хороший historical baseline?

## Methodology
- Какая временная гранулярность лучше: неделя, месяц, квартал?
- Как формально определять `first_seen` semantic cluster?
- Какие веса Emerging Score дают устойчивый ranking?
- Как нормализовать counts между evidence types?
- Как считать независимость source/actor?

## ML
- Qwen3-Embedding-0.6B vs BGE-M3 на нашем corpus?
- Нужен ли reranker уже в MVP?
- HDBSCAN vs другой incremental clustering подход?
- Как хранить/update cluster centroids?
- Когда удалять document embeddings?

## Product
- Нужна ли пользователю настройка временного горизонта?
- Показывать ли raw methodology score components в первой версии?
- Как визуально объяснить difference popularity vs emergence?
