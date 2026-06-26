---
name: collect-data-show
description: Collect, compile, and visualize user-owned structured data through one workflow. Use when the user asks to collect a data source and show it visually, organize saved/favorite/bookmark data, build a local knowledge dashboard, process Zhihu favorites, turn JSON/CSV/Markdown lists into a searchable card interface, or chain data acquisition with a generated local HTML viewer.
---

# Collect Data Show

## Purpose

Use one public skill entrypoint for the full pipeline:

1. Collect or accept data.
2. Normalize and compile it.
3. Classify and enrich it with the active Codex model by default for interactive knowledge-library workflows.
4. Generate a local visual dashboard.
5. Serve it locally when useful.

Keep source-specific logic inside scripts and routing rules. Do not expose separate user-facing skills for every source or display template.

Do not require the user to mention which model performs classification. In interactive Codex sessions, the active assistant model is the default classifier. The user-facing request should stay natural, such as "整理知乎收藏并展示" or "继续处理这个知识库".

Do not tell the user to run internal Python scripts as the primary usage path. The scripts are implementation details for Codex to execute. User-facing instructions should be natural skill requests, such as:

- `使用 collect-data-show，整理知乎收藏并展示。`
- `使用 collect-data-show，整理 B 站收藏并展示。`
- `使用 collect-data-show，继续处理这个知识库。`

## Architecture

`collect-data-show` is the only user-facing skill. Individual platforms are internal source adapters, not separate skills.

Pipeline:

1. Source adapter collects user-owned data from one platform.
2. Source compiler normalizes raw platform data into the shared `items.json` schema.
3. Codex-agent classification enriches the normalized items.
4. The shared dashboard generator renders the result.

Examples of source adapters:

- Zhihu favorites
- Bilibili favorites
- Douyin favorites
- Browser bookmarks
- Existing JSON/CSV/Markdown files

Do not create separate skills such as `zhihu-collector` or `bilibili-collector`. Add platform capabilities under this skill and keep their output compatible with the shared viewer.

Canonical item fields:

```json
{
  "id": "stable source id or url",
  "title": "item title",
  "url": "source link",
  "author": "creator/author/uploader",
  "category": "high-level classification",
  "topic": "specific topic",
  "concepts": ["tags", "concepts"],
  "collections": ["source folder names"],
  "summary": "excerpt or generated summary",
  "reason": "why this item is useful",
  "readingPriority": "精读/略读/待判断",
  "source": "zhihu/bilibili/douyin/...",
  "sourceType": "article/video/bookmark/...",
  "cover": "optional image or video cover url"
}
```

## Routing

### Zhihu Favorites

Use this route when the user asks for:

- 获取知乎收藏
- 整理知乎收藏
- 编译知乎收藏
- 把知乎收藏做成可视化页面

If the user already has an export:

```bash
python3 ~/.codex/skills/collect-data-show/scripts/compile_zhihu_favorites.py INPUT_FILE --output OUTPUT_DIR
python3 ~/.codex/skills/collect-data-show/scripts/refresh_zhihu_artifacts.py OUTPUT_DIR/items.json
python3 ~/.codex/skills/collect-data-show/scripts/generate_data_viewer.py OUTPUT_DIR/items.json --output OUTPUT_DIR --title "知乎收藏知识库" --force
```

If the user wants Codex to collect from Zhihu:

```bash
python3 ~/.codex/skills/collect-data-show/scripts/run_collect_data_show.py zhihu --output-dir OUTPUT_DIR
```

Use a dedicated browser profile. If login or captcha appears, pause and let the user finish verification. Never bypass login, captcha, or platform restrictions.

This main route performs the full pipeline:

- collect all available Zhihu favorite folders
- compile and dedupe items
- let the active Codex agent classify items from titles/summaries when running interactively
- refresh graph/Markdown index artifacts
- generate the local dashboard

The user has defined AI classification as part of this skill's job. Do not ask the user to specify the model. In an interactive Codex session, do not call a separate OpenAI API just to classify; use the active assistant model to classify batches, write the results back to `items.json`, then refresh the generated artifacts. For unattended command-line automation only, `classify_items_ai.py` can call the configured API when explicitly requested.

### Bilibili Favorites

Use this route when the user asks for:

- 获取 B 站收藏
- 整理 bilibili 收藏
- 把 B 站收藏做成知识库
- 展示 B 站收藏夹内容

Run the Bilibili source adapter through the main runner:

```bash
python3 ~/.codex/skills/collect-data-show/scripts/run_collect_data_show.py bilibili --output-dir OUTPUT_DIR
```

The Bilibili adapter performs the same source pipeline as Zhihu:

- open a dedicated browser profile
- let the user manually log in or complete verification when needed
- collect favorite folders and video metadata visible to the user
- compile raw platform data into the shared `items.json` schema
- generate the shared dashboard

Do not download videos, comments, danmaku, or private content that the logged-in user cannot normally access. Keep Bilibili as a source adapter under this skill, not a separate skill.

### Existing Structured Data

Use this route when the user provides JSON, CSV, or Markdown list data and wants a visual page:

```bash
python3 ~/.codex/skills/collect-data-show/scripts/generate_data_viewer.py INPUT_FILE --output OUTPUT_DIR --title "Dashboard Title"
```

Supported inputs:

- JSON list
- JSON object with `items`, `data`, `results`, or `records`
- CSV with a header row
- Markdown headings with `[title](url)` links

### Regenerate Viewer Only

Use this route when normalized data already exists and only the UI needs rebuilding:

```bash
python3 ~/.codex/skills/collect-data-show/scripts/generate_data_viewer.py ITEMS_JSON --output OUTPUT_DIR --title "Dashboard Title" --force
```

If the user has manually customized `style.css` or `app.js`, do not overwrite without confirming or backing up.

## Dashboard Output

The generated dashboard includes:

- Sidebar categories
- Concept/tag cloud
- Topic chips
- Search
- Priority filtering
- Card grid
- Detail pane
- Clickable source links
- Markdown export for the current filtered view

## AI Classification

AI classification is the default for knowledge libraries. Keyword classification is only a local/offline bootstrap fallback produced during compilation and will misclassify mixed-domain articles.

Interactive Codex mode, default whenever Codex is in a conversation:

- Read compact batches from `items.json`: `idx`, `title`, `author`, `summary`, `collections`, and old category.
- Classify with the active assistant model in the conversation.
- Use source-aware signals. For Bilibili videos, title, uploader, source folder, duration, and description are often more important than an old category. For Zhihu articles, title and excerpt are usually the strongest signals.
- Write back `category`, `topic`, `concepts`, `readingPriority`, `reason`, `classificationConfidence`, and `classificationMethod: "codex-agent"`.
- Let `apply_agent_classification.py` refresh graph and Markdown artifacts after writing classifications.

Use the helper scripts for the interactive loop:

```bash
python3 ~/.codex/skills/collect-data-show/scripts/export_agent_classification_batch.py ITEMS_JSON --output BATCH_JSON --limit 60
python3 ~/.codex/skills/collect-data-show/scripts/apply_agent_classification.py ITEMS_JSON UPDATES_JSON
```

Repeat until `export_agent_classification_batch.py` returns an empty batch. Keep batch sizes small enough that Codex can reason about titles instead of mechanically pattern matching.

Unattended API mode, only when explicitly requested by the user or a non-interactive automation need:

```bash
python3 ~/.codex/skills/collect-data-show/scripts/classify_items_ai.py ITEMS_JSON --output ITEMS_JSON
```

The API classifier sends batched item metadata to the OpenAI Responses API:

- title
- author
- summary excerpt
- source collections
- existing category/concepts

It writes:

- `category`
- `topic`
- `concepts`
- `readingPriority`
- `reason`
- `classificationConfidence`
- `classificationMethod`

Default model comes from `OPENAI_MODEL`, falling back to `gpt-5.4-mini`. Use `--model` to override.

Serve locally:

```bash
cd OUTPUT_DIR && python3 -m http.server 8765 --bind 127.0.0.1
```

Then provide:

```text
http://127.0.0.1:8765/index.html
```

If port `8765` is occupied, choose another free port.

## Configuration

The viewer reads `config.json`. If field inference is wrong, edit `config.json` rather than rewriting the template.

Important mappings:

```json
{
  "fields": {
    "title": "title",
    "url": "url",
    "author": "author",
    "category": "category",
    "summary": "summary",
    "concepts": "concepts",
    "priority": "readingPriority"
  }
}
```

Dot paths are supported, such as `owner.login`.

## Privacy Rules

- Keep data local by default.
- Do not read a user's daily browser profile unless explicitly asked.
- Do not save service passwords.
- Do not bypass login, captcha, paywalls, or access controls.
- In interactive Codex mode, prefer classifying with the active assistant model instead of a separate API call.
- Only send item metadata to a configured external AI provider when the user explicitly requests unattended/API classification.
- Do not send full article bodies, browser cookies, passwords, or unrelated local files to external APIs.

## Resources

- `scripts/collect_zhihu_favorites.py`: collect Zhihu favorites with a controlled browser session.
- `scripts/compile_zhihu_favorites.py`: normalize Zhihu exports into `items.json`, `index.md`, `reading-plan.md`, and `graph.json`.
- `scripts/collect_bilibili_favorites.py`: collect Bilibili favorite folders and video metadata with a controlled browser session.
- `scripts/compile_bilibili_favorites.py`: normalize Bilibili exports into the shared item schema.
- `scripts/export_agent_classification_batch.py`: export compact batches for the active Codex model to classify.
- `scripts/apply_agent_classification.py`: apply Codex-agent classification updates and refresh artifacts.
- `scripts/classify_items_ai.py`: use an OpenAI model to classify and enrich normalized items.
- `scripts/run_collect_data_show.py`: main pipeline runner for source-specific collection, AI classification, and dashboard generation.
- `scripts/refresh_zhihu_artifacts.py`: rebuild `graph.json`, `index.md`, and `reading-plan.md` from classified `items.json`.
- `scripts/generate_data_viewer.py`: generate a static dashboard from JSON/CSV/Markdown data.
- `assets/static-dashboard/`: reusable viewer template.
- `references/zhihu-output-schema.md`: schema notes for Zhihu compilation outputs.
