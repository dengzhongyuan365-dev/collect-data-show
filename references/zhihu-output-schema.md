# Output Schema

## items.json

Array of normalized items:

```json
{
  "id": "https://www.zhihu.com/question/1/answer/2",
  "title": "文章标题",
  "url": "https://www.zhihu.com/question/1/answer/2",
  "author": "作者",
  "category": "AI 与技术",
  "tags": ["AI", "算法"],
  "collections": ["我的收藏"],
  "summary": "摘要",
  "readingPriority": "精读"
}
```

## graph.json

```json
{
  "nodes": [
    { "id": "article:https://...", "type": "article", "label": "标题" },
    { "id": "category:AI 与技术", "type": "category", "label": "AI 与技术" },
    { "id": "concept:算法", "type": "concept", "label": "算法" }
  ],
  "edges": [
    { "source": "article:https://...", "target": "category:AI 与技术", "type": "categorized_as" },
    { "source": "article:https://...", "target": "concept:算法", "type": "mentions" }
  ]
}
```

## Markdown Outputs

- `index.md`: human-readable topic index grouped by category.
- `reading-plan.md`: prioritized queue grouped by 精读 / 略读 / 待判断.
