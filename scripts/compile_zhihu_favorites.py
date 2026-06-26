#!/usr/bin/env python3
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


CATEGORY_RULES = [
    ("AI 与技术", ["ai", "人工智能", "大模型", "模型", "prompt", "agent", "机器学习", "深度学习", "算法", "编程", "代码", "程序", "linux", "数据库", "架构", "开源"]),
    ("软件与工具", ["软件", "工具", "网站", "效率", "插件", "浏览器", "剪辑", "图片", "音效", "素材", "windows", "mac", "电脑"]),
    ("产品与设计", ["产品", "设计", "交互", "用户", "体验", "增长", "运营", "需求", "商业模式", "saas", "创业"]),
    ("商业与投资", ["投资", "股票", "基金", "经济", "金融", "公司", "企业", "财务", "估值", "市场", "消费", "生意"]),
    ("历史与文化", ["历史", "古代", "文化", "文学", "哲学", "考古", "战争", "王朝", "制度", "传统", "汉字"]),
    ("心理与成长", ["心理", "成长", "认知", "学习", "习惯", "情绪", "焦虑", "效率", "思维", "人生", "选择"]),
    ("生活与健康", ["生活", "健康", "医学", "疾病", "饮食", "运动", "睡眠", "家庭", "买房", "装修", "城市"]),
    ("职业与教育", ["职业", "工作", "面试", "简历", "职场", "教育", "大学", "考研", "考试", "课程", "老师", "论文"]),
    ("社会与观点", ["社会", "法律", "政策", "新闻", "观点", "争议", "道德", "舆论", "公共", "事件"]),
]

CONCEPTS = [
    "AI", "大模型", "Agent", "Prompt", "机器学习", "深度学习", "算法", "Python", "Java", "Linux",
    "开源", "数据库", "架构", "产品", "设计", "创业", "投资", "股票", "基金", "历史", "哲学",
    "心理", "学习", "效率", "写作", "论文", "工具", "软件", "剪辑", "健康", "职场", "面试",
]


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def split_zh_list(value):
    if not value:
        return []
    parts = re.split(r"[、,，;；]\s*", value)
    result = []
    seen = set()
    for part in parts:
        text = clean_text(part)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def load_items(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return normalize_json_items(json.loads(text))
    return parse_markdown_items(text)


def normalize_json_items(payload):
    raw_items = payload.get("items", payload) if isinstance(payload, dict) else payload
    items = []
    for raw in raw_items if isinstance(raw_items, list) else []:
        refs = raw.get("collectionRefs") or []
        collections = [ref.get("title") for ref in refs if isinstance(ref, dict) and ref.get("title")]
        if raw.get("collectionTitle"):
            collections.append(raw["collectionTitle"])
        item = {
            "id": raw.get("id") or raw.get("url"),
            "title": clean_text(raw.get("title")),
            "url": raw.get("url") or raw.get("id"),
            "author": clean_text(raw.get("author")),
            "category": clean_text(raw.get("category")),
            "tags": unique_list(raw.get("tags") or []),
            "collections": unique_list(collections),
            "summary": clean_text(raw.get("summary") or raw.get("excerpt")),
            "reason": clean_text(raw.get("reason")),
            "readingPriority": clean_text(raw.get("readingPriority")),
        }
        if item["url"] and item["title"]:
            items.append(item)
    return dedupe_items(items)


def parse_markdown_items(text):
    items = []
    current_category = ""
    current = None
    summary_lines = []
    in_summary = False

    def flush():
        nonlocal current, summary_lines, in_summary
        if not current:
            return
        if summary_lines and not current.get("summary"):
            current["summary"] = clean_text(" ".join(summary_lines))
        if current.get("url") and current.get("title"):
            items.append(current)
        current = None
        summary_lines = []
        in_summary = False

    for line in text.splitlines():
        raw = line.rstrip()
        if raw.startswith("## "):
            flush()
            current_category = clean_text(raw[3:])
            continue
        match = re.match(r"^### \[(.+?)\]\((.+?)\)", raw)
        if match:
            flush()
            current = {
                "id": match.group(2),
                "title": clean_text(match.group(1)),
                "url": match.group(2),
                "author": "",
                "category": current_category,
                "tags": [],
                "collections": [],
                "summary": "",
                "reason": "",
                "readingPriority": "",
            }
            continue
        if not current:
            continue
        if raw.startswith("作者："):
            current["author"] = clean_text(raw.removeprefix("作者："))
        elif raw.startswith("阅读优先级："):
            current["readingPriority"] = clean_text(raw.removeprefix("阅读优先级："))
        elif raw.startswith("标签："):
            current["tags"] = split_zh_list(raw.removeprefix("标签："))
        elif raw.startswith("来源收藏夹："):
            current["collections"] = split_zh_list(raw.removeprefix("来源收藏夹："))
        elif raw.startswith("保留理由："):
            current["reason"] = clean_text(raw.removeprefix("保留理由："))
            in_summary = False
        elif raw.strip():
            in_summary = True
            if in_summary:
                summary_lines.append(raw)

    flush()
    return dedupe_items(items)


def dedupe_items(items):
    by_url = {}
    for item in items:
        url = item["url"]
        if url not in by_url:
            by_url[url] = item
            continue
        old = by_url[url]
        old["collections"] = unique_list(old.get("collections", []) + item.get("collections", []))
        old["tags"] = unique_list(old.get("tags", []) + item.get("tags", []))
        for key in ["author", "category", "summary", "reason", "readingPriority"]:
            if not old.get(key) and item.get(key):
                old[key] = item[key]
    return list(by_url.values())


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


def classify_item(item):
    if item.get("category") and item["category"] != "未分类":
        return item["category"]
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    scored = []
    for category, keywords in CATEGORY_RULES:
        score = sum(1 for keyword in keywords if keyword.lower() in text)
        scored.append((score, category))
    scored.sort(reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else "未分类"


def extract_concepts(item):
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    concepts = list(item.get("tags", []))
    lower = text.lower()
    for concept in CONCEPTS:
        if concept.lower() in lower or concept in text:
            concepts.append(concept)
    return unique_list(concepts)[:8]


def enrich_items(items):
    for item in items:
        item["category"] = classify_item(item)
        item["concepts"] = extract_concepts(item)
        if not item.get("readingPriority"):
            item["readingPriority"] = infer_priority(item)
    return items


def infer_priority(item):
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    if re.search(r"系统|完整|指南|教程|深度|复盘|原理|方法|总结|实践|经验|论文|算法", text):
        return "精读"
    if len(text) < 40:
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
        article_id = f"article:{item['url']}"
        node(article_id, "article", item["title"], url=item["url"], author=item.get("author", ""))

        category = item.get("category") or "未分类"
        category_id = f"category:{category}"
        node(category_id, "category", category)
        edge(article_id, category_id, "categorized_as")

        for collection in item.get("collections", []):
            collection_id = f"collection:{collection}"
            node(collection_id, "collection", collection)
            edge(collection_id, article_id, "contains")

        for concept in item.get("concepts", []):
            concept_id = f"concept:{concept}"
            node(concept_id, "concept", concept)
            edge(article_id, concept_id, "mentions")

    return {"nodes": list(nodes.values()), "edges": edges}


def write_index(items, output_dir):
    by_category = defaultdict(list)
    for item in items:
        by_category[item.get("category") or "未分类"].append(item)

    lines = ["# 知乎收藏知识索引", "", f"共 {len(items)} 条收藏。", ""]
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
                meta.append(f"作者：{item['author']}")
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
                lines.append(f"  - 摘要：{item['summary'][:180]}")
        lines.append("")

    (output_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def write_reading_plan(items, output_dir):
    groups = defaultdict(list)
    for item in items:
        groups[item.get("readingPriority") or "待判断"].append(item)

    order = ["精读", "略读", "待判断"]
    lines = ["# 知乎收藏学习清单", ""]
    for priority in order:
        group = groups.get(priority, [])
        lines.append(f"## {priority}（{len(group)}）")
        lines.append("")
        for item in sorted(group, key=lambda value: value.get("category", "")):
            lines.append(f"- [{item['title']}]({item['url']}) - {item.get('category') or '未分类'}")
        lines.append("")
    (output_dir / "reading-plan.md").write_text("\n".join(lines), encoding="utf-8")


def compile_favorites(input_path, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    items = enrich_items(load_items(input_path))
    graph = build_graph(items)

    (output_dir / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index(items, output_dir)
    write_reading_plan(items, output_dir)
    return items, graph


def main():
    parser = argparse.ArgumentParser(description="Compile Zhihu favorites export into knowledge index files.")
    parser.add_argument("input", type=Path, help="Path to Zhihu favorites JSON or Markdown export.")
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
