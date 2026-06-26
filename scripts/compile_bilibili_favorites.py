#!/usr/bin/env python3
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


CONCEPTS = [
    "AI", "大模型", "Agent", "编程", "Python", "Java", "C++", "Linux", "开源", "数据库",
    "架构", "算法", "产品", "设计", "创业", "投资", "历史", "哲学", "心理", "学习",
    "效率", "写作", "工具", "软件", "剪辑", "音乐", "游戏", "影视", "科普", "生活",
]


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_items(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_items = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        return []
    return dedupe_items([normalize_item(raw) for raw in raw_items])


def normalize_item(raw):
    refs = raw.get("collectionRefs") or []
    collections = [ref.get("title") for ref in refs if isinstance(ref, dict) and ref.get("title")]
    if raw.get("collectionTitle"):
        collections.append(raw["collectionTitle"])

    bvid = clean_text(raw.get("bvid") or raw.get("bvId") or raw.get("bvidStr"))
    aid = raw.get("aid") or raw.get("id")
    url = clean_text(raw.get("url"))
    if not url:
        if bvid:
            url = f"https://www.bilibili.com/video/{bvid}"
        elif aid:
            url = f"https://www.bilibili.com/video/av{aid}"

    item = {
        "id": bvid or str(aid or url),
        "title": clean_text(raw.get("title")),
        "url": url,
        "author": clean_text(raw.get("author") or raw.get("upperName")),
        "category": clean_text(raw.get("category") or "未分类"),
        "topic": clean_text(raw.get("topic")),
        "tags": unique_list(raw.get("tags") or []),
        "collections": unique_list(collections),
        "summary": clean_text(raw.get("summary") or raw.get("intro") or raw.get("description")),
        "reason": clean_text(raw.get("reason")),
        "readingPriority": clean_text(raw.get("readingPriority")),
        "concepts": unique_list(raw.get("concepts") or []),
        "source": "bilibili",
        "sourceType": clean_text(raw.get("sourceType") or "video"),
        "cover": normalize_cover(raw.get("cover") or raw.get("pic")),
        "duration": raw.get("duration"),
        "pubTime": raw.get("pubTime") or raw.get("pubtime"),
        "favTime": raw.get("favTime") or raw.get("fav_time"),
        "playCount": raw.get("playCount") or raw.get("cnt_info", {}).get("play"),
        "danmakuCount": raw.get("danmakuCount") or raw.get("cnt_info", {}).get("danmaku"),
    }
    if not item["concepts"]:
        item["concepts"] = extract_concepts(item)
    if not item["readingPriority"]:
        item["readingPriority"] = infer_priority(item)
    return item


def normalize_cover(value):
    text = clean_text(value)
    if text.startswith("//"):
        return f"https:{text}"
    if re.match(r"^http://i\d\.hdslb\.com/", text):
        return re.sub(r"^http:", "https:", text)
    return text


def dedupe_items(items):
    by_key = {}
    for item in items:
        if not item.get("title") or not item.get("url"):
            continue
        key = item.get("id") or item["url"]
        if key not in by_key:
            by_key[key] = item
            continue
        old = by_key[key]
        old["collections"] = unique_list(old.get("collections", []) + item.get("collections", []))
        old["tags"] = unique_list(old.get("tags", []) + item.get("tags", []))
        old["concepts"] = unique_list(old.get("concepts", []) + item.get("concepts", []))
        for field in ["author", "summary", "cover", "duration", "pubTime", "favTime", "playCount", "danmakuCount"]:
            if not old.get(field) and item.get(field):
                old[field] = item[field]
    return list(by_key.values())


def unique_list(values):
    result = []
    seen = set()
    for value in values:
        text = clean_text(value)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def extract_concepts(item):
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    lower = text.lower()
    concepts = list(item.get("tags", []))
    for concept in CONCEPTS:
        if concept.lower() in lower or concept in text:
            concepts.append(concept)
    return unique_list(concepts)[:8]


def infer_priority(item):
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    if re.search(r"教程|指南|系统|完整|原理|源码|深度|公开课|课程|学习|实践|项目|复盘", text):
        return "精读"
    if len(text) < 30:
        return "待判断"
    return "略读"


def build_graph(items):
    nodes = {}
    edges = []

    def node(node_id, node_type, label, **extra):
        nodes[node_id] = {"id": node_id, "type": node_type, "label": label, **extra}

    def edge(source, target, edge_type):
        edges.append({"source": source, "target": target, "type": edge_type})

    for item in items:
        item_id = f"item:{item['url']}"
        node(item_id, item.get("sourceType") or "item", item["title"], url=item["url"], author=item.get("author", ""))

        category = item.get("category") or "未分类"
        category_id = f"category:{category}"
        node(category_id, "category", category)
        edge(item_id, category_id, "categorized_as")

        for collection in item.get("collections", []):
            collection_id = f"collection:{collection}"
            node(collection_id, "collection", collection)
            edge(collection_id, item_id, "contains")

        for concept in item.get("concepts", []):
            concept_id = f"concept:{concept}"
            node(concept_id, "concept", concept)
            edge(item_id, concept_id, "mentions")

    return {"nodes": list(nodes.values()), "edges": edges}


def write_index(items, output_dir):
    by_category = defaultdict(list)
    for item in items:
        by_category[item.get("category") or "未分类"].append(item)

    lines = ["# B 站收藏知识索引", "", f"共 {len(items)} 条收藏。", ""]
    for category, group in sorted(by_category.items(), key=lambda entry: (-len(entry[1]), entry[0])):
        concepts = Counter(concept for item in group for concept in item.get("concepts", []))
        lines.append(f"## {category}")
        lines.append("")
        if concepts:
            lines.append("高频概念：" + "、".join(name for name, _count in concepts.most_common(12)))
            lines.append("")
        for item in group:
            meta = []
            if item.get("author"):
                meta.append(f"UP主：{item['author']}")
            if item.get("readingPriority"):
                meta.append(f"优先级：{item['readingPriority']}")
            if item.get("collections"):
                meta.append("来源：" + "、".join(item["collections"]))
            lines.append(f"- [{item['title']}]({item['url']})")
            if meta:
                lines.append(f"  - {'；'.join(meta)}")
            if item.get("concepts"):
                lines.append(f"  - 概念：{'、'.join(item['concepts'])}")
            if item.get("summary"):
                lines.append(f"  - 简介：{item['summary'][:180]}")
        lines.append("")

    (output_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def write_reading_plan(items, output_dir):
    groups = defaultdict(list)
    for item in items:
        groups[item.get("readingPriority") or "待判断"].append(item)

    lines = ["# B 站收藏观看清单", ""]
    for priority in ["精读", "略读", "待判断"]:
        group = groups.get(priority, [])
        lines.append(f"## {priority}（{len(group)}）")
        lines.append("")
        for item in sorted(group, key=lambda value: value.get("category", "")):
            lines.append(f"- [{item['title']}]({item['url']}) - {item.get('category') or '未分类'}")
        lines.append("")
    (output_dir / "reading-plan.md").write_text("\n".join(lines), encoding="utf-8")


def compile_favorites(input_path, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    items = load_items(input_path)
    graph = build_graph(items)

    (output_dir / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index(items, output_dir)
    write_reading_plan(items, output_dir)
    return items, graph


def main():
    parser = argparse.ArgumentParser(description="Compile Bilibili favorites export into shared knowledge index files.")
    parser.add_argument("input", type=Path, help="Path to Bilibili favorites JSON export.")
    parser.add_argument("--output", type=Path, help="Output directory. Defaults to INPUT_NAME-compiled beside input.")
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    output_dir = args.output.expanduser().resolve() if args.output else input_path.with_name(f"{input_path.stem}-compiled")
    items, graph = compile_favorites(input_path, output_dir)
    print(f"Compiled {len(items)} items")
    print(f"Graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
