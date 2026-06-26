#!/usr/bin/env python3
import argparse
import csv
import json
import re
import shutil
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_DIR = SKILL_DIR / "assets" / "static-dashboard"


FIELD_CANDIDATES = {
    "id": ["id", "uuid", "key", "url", "link"],
    "title": ["title", "name", "label", "heading", "question", "repo", "项目", "标题", "名称"],
    "url": ["url", "link", "href", "html_url", "source", "链接", "地址"],
    "author": ["author", "owner", "creator", "user", "publisher", "作者", "创建者"],
    "category": ["category", "type", "group", "section", "language", "分类", "类型"],
    "collections": ["collections", "collection", "folder", "folders", "sourceCollection", "来源", "收藏夹"],
    "summary": ["summary", "description", "excerpt", "abstract", "content", "body", "简介", "摘要", "描述"],
    "reason": ["reason", "note", "notes", "comment", "保留理由", "备注"],
    "priority": ["readingPriority", "priority", "rank", "level", "优先级"],
    "concepts": ["concepts", "tags", "topics", "keywords", "labels", "标签", "概念", "关键词"],
    "topic": ["topic", "topicName", "subject", "theme", "专题", "主题"],
}


def main():
    parser = argparse.ArgumentParser(description="Generate a local searchable data dashboard.")
    parser.add_argument("input", help="Input JSON, CSV, or Markdown file")
    parser.add_argument("--output", "-o", required=True, help="Output directory")
    parser.add_argument("--title", default=None, help="Dashboard title")
    parser.add_argument("--description", default="把结构化数据变成可以浏览、搜索和导出的资料库")
    parser.add_argument("--force", action="store_true", help="Overwrite output files if they exist")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    items = load_items(input_path)
    if not items:
        raise SystemExit("No items found in input file.")

    fields = infer_fields(items)
    title = args.title or infer_title(input_path)
    prepare_output(output_dir, args.force)

    for filename in ["index.html", "app.js", "style.css"]:
        shutil.copy2(TEMPLATE_DIR / filename, output_dir / filename)

    write_json(output_dir / "items.json", items)
    write_json(output_dir / "config.json", build_config(title, args.description, fields))

    print(f"Generated dashboard: {output_dir / 'index.html'}")
    print("Serve it with:")
    print(f"  cd {output_dir} && python3 -m http.server 8765 --bind 127.0.0.1")


def load_items(path):
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ["items", "data", "results", "records"]:
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [data]
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if suffix in {".md", ".markdown"}:
        return parse_markdown_links(path.read_text(encoding="utf-8"))
    raise SystemExit(f"Unsupported input type: {path.suffix}")


def parse_markdown_links(text):
    items = []
    category = "未分类"
    for line in text.splitlines():
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            category = heading.group(2).strip()
            continue
        link = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", line)
        if link:
            items.append({
                "title": link.group(1).strip(),
                "url": link.group(2).strip(),
                "category": category,
                "summary": line.strip(),
            })
    return items


def infer_fields(items):
    keys = collect_keys(items[:100])
    lower_map = {key.lower(): key for key in keys}
    fields = {}
    for target, candidates in FIELD_CANDIDATES.items():
        fields[target] = pick_field(candidates, lower_map) or target
    return fields


def collect_keys(items):
    keys = set()
    for item in items:
        keys.update(flatten_keys(item))
    return sorted(keys)


def flatten_keys(obj, prefix=""):
    keys = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.append(path)
            if isinstance(value, dict):
                keys.extend(flatten_keys(value, path))
    return keys


def pick_field(candidates, lower_map):
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    for candidate in candidates:
        for lower_key, original_key in lower_map.items():
            if candidate.lower() in lower_key:
                return original_key
    return None


def infer_title(path):
    return path.stem.replace("-", " ").replace("_", " ").strip().title() or "数据展示工作台"


def build_config(title, description, fields):
    return {
        "title": title,
        "description": description,
        "dataFile": "items.json",
        "graphFile": "graph.json",
        "fields": fields,
        "labels": {
            "item": "条目",
            "allItems": "全部条目",
            "category": "分类",
            "concept": "概念",
            "source": "来源",
            "reason": "说明",
            "summary": "摘要",
            "openOriginal": "打开链接",
            "exportFilename": "data-view.md",
        },
    }


def prepare_output(output_dir, force):
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = ["index.html", "app.js", "style.css", "items.json", "config.json"]
    existing = [name for name in targets if (output_dir / name).exists()]
    if existing and not force:
        names = ", ".join(existing)
        raise SystemExit(f"Output files already exist ({names}). Use --force to overwrite.")


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
