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
        "title": clean_text(item.get("title", "")),
        "author": clean_text(item.get("author", "")),
        "summary": truncate(item.get("summary", ""), summary_chars),
        "collections": item.get("collections", []),
        "oldCategory": item.get("category", ""),
        "oldConcepts": item.get("concepts", []),
        "oldPriority": item.get("readingPriority", ""),
    }


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def truncate(value, max_length):
    text = clean_text(value)
    return text[:max_length]


if __name__ == "__main__":
    main()
