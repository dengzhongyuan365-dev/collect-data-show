#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


CLASSIFIED_METHODS = {"codex-agent", "ai"}


def main():
    parser = argparse.ArgumentParser(description="Export a compact batch for Codex-agent classification.")
    parser.add_argument("items", type=Path, help="Path to items.json")
    parser.add_argument("--output", "-o", type=Path, help="Write batch JSON to this file. Defaults to stdout.")
    parser.add_argument("--start", type=int, default=0, help="Start scanning from this item index.")
    parser.add_argument("--limit", type=int, default=60, help="Maximum number of items to export.")
    parser.add_argument("--all", action="store_true", help="Include already agent/API classified items.")
    parser.add_argument("--summary-chars", type=int, default=180)
    args = parser.parse_args()

    items_path = args.items.expanduser().resolve()
    items = json.loads(items_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("items.json must be a JSON array.")

    batch = []
    for idx, item in enumerate(items):
        if idx < args.start:
            continue
        method = item.get("classificationMethod")
        if not args.all and method in CLASSIFIED_METHODS:
            continue
        batch.append(compact_item(idx, item, args.summary_chars))
        if len(batch) >= args.limit:
            break

    payload = {
        "source": str(items_path),
        "totalItems": len(items),
        "start": args.start,
        "count": len(batch),
        "classificationGuidance": build_guidance(batch),
        "classificationSchema": {
            "category": [
                "AI 与技术",
                "软件与工具",
                "产品与设计",
                "职业与教育",
                "心理与成长",
                "历史与文化",
                "商业与投资",
                "生活与健康",
                "社会与观点",
                "文艺与娱乐",
                "未分类",
            ],
            "readingPriority": ["精读", "略读", "待判断"],
            "requiredUpdateFields": [
                "idx",
                "category",
                "topic",
                "concepts",
                "readingPriority",
                "reason",
                "classificationConfidence",
            ],
        },
        "items": batch,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        print(f"Exported {len(batch)} items: {output_path}")
    else:
        print(text)


def compact_item(idx, item, summary_chars):
    return {
        "idx": idx,
        "source": clean_text(item.get("source", "")),
        "sourceType": clean_text(item.get("sourceType", "")),
        "title": clean_text(item.get("title", "")),
        "author": clean_text(item.get("author", "")),
        "summary": truncate(item.get("summary", ""), summary_chars),
        "collections": item.get("collections", []),
        "oldCategory": item.get("category", ""),
        "oldTopic": item.get("topic", ""),
        "oldConcepts": item.get("concepts", []),
        "oldPriority": item.get("readingPriority", ""),
        "duration": item.get("duration"),
    }


def build_guidance(batch):
    sources = {item.get("source") for item in batch if item.get("source")}
    if "bilibili" in sources:
        return {
            "mode": "video-favorites",
            "rules": [
                "这是 B 站视频收藏。主要根据标题、UP 主、简介和收藏夹判断分类。",
                "技术教程、编程、操作系统、C/C++、Linux、AI、工具链归入 AI 与技术。",
                "做菜、健身、身体健康、日常生活技能归入 生活与健康。",
                "音乐、游戏、影视解说、搞笑娱乐归入 文艺与娱乐。",
                "历史人物、古诗词、传统文化、社会制度史归入 历史与文化。",
                "职场、面试、课程学习、学习方法归入 职业与教育。",
                "焦虑、习惯、自我改变、人际关系归入 心理与成长。",
                "分类要根据实际主题判断，不要被默认收藏夹名称误导。",
            ],
        }
    if "zhihu" in sources:
        return {
            "mode": "article-favorites",
            "rules": [
                "这是知乎收藏。主要根据标题判断，摘要和收藏夹辅助。",
                "技术文章出现历史、哲学、设计等词时，不要轻易改到历史文化或产品设计。",
            ],
        }
    return {
        "mode": "generic-items",
        "rules": ["根据标题、摘要、来源集合和旧标签判断分类。"],
    }


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def truncate(value, max_length):
    text = clean_text(value)
    return text[:max_length]


if __name__ == "__main__":
    main()
