# collect-data-show

A Codex skill for collecting user-owned data, compiling it into a local knowledge library, and generating a searchable static dashboard.

Current workflows include:

- Zhihu favorites collection through a user-controlled browser session.
- Bilibili favorites collection through a user-controlled browser session.
- Normalization into `items.json`, `graph.json`, `index.md`, and `reading-plan.md`.
- Interactive Codex-agent classification for categories, topics, concepts, and reading priority.
- Static dashboard generation for JSON/CSV/Markdown data.

The intended architecture is one main skill with multiple internal source adapters. Zhihu, Bilibili, Douyin, browser bookmarks, and existing files should all compile into the same item schema, then reuse the same classification and dashboard pipeline.

This repository contains only the reusable skill, scripts, and dashboard template. Personal exports and generated knowledge libraries should be stored in a separate private repository.

## Install

Clone this repository into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/YOUR_NAME/collect-data-show.git ~/.codex/skills/collect-data-show
```

Then invoke it naturally in Codex, for example:

```text
使用 collect-data-show，整理知乎收藏并展示。
```

or:

```text
使用 collect-data-show，整理 B 站收藏并展示。
```

## Privacy

The skill uses a dedicated browser profile for collection and does not save passwords. Do not commit generated personal data such as `items.json`, `graph.json`, raw exports, or dashboard output to this public repository.
