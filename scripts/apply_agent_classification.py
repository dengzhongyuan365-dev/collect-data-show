#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from compile_zhihu_favorites import build_graph, write_index, write_reading_plan


CATEGORIES = {
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
}

PRIORITIES = {"精读", "略读", "待判断"}


def main():
    parser = argparse.ArgumentParser(description="Apply Codex-agent classification updates to items.json.")
    parser.add_argument("items", type=Path, help="Path to items.json")
    parser.add_argument("updates", type=Path, help="Classification updates JSON")
    parser.add_argument("--no-refresh", action="store_true", help="Do not rebuild graph/index artifacts.")
    args = parser.parse_args()

    items_path = args.items.expanduser().resolve()
    updates_path = args.updates.expanduser().resolve()
    items = json.loads(items_path.read_text(encoding="utf-8"))
    updates_payload = json.loads(updates_path.read_text(encoding="utf-8"))
    updates = updates_payload.get("items", updates_payload) if isinstance(updates_payload, dict) else updates_payload

    if not isinstance(items, list):
        raise SystemExit("items.json must be a JSON array.")
    if not isinstance(updates, list):
        raise SystemExit("updates must be a JSON array or an object with an items array.")

    applied = 0
    for update in updates:
        validate_update(update, len(items))
        item = items[update["idx"]]
        item["category"] = update["category"]
        item["topic"] = clean_text(update["topic"])
        item["concepts"] = unique_list(update.get("concepts", []))[:8]
        item["readingPriority"] = update["readingPriority"]
        item["reason"] = clean_text(update["reason"])
        item["classificationConfidence"] = float(update["classificationConfidence"])
        item["classificationMethod"] = "codex-agent"
        applied += 1

    items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_refresh:
        refresh_artifacts(items_path, items)

    print(f"Applied {applied} classification updates: {items_path}")


def validate_update(update, total):
    if not isinstance(update, dict):
        raise SystemExit("each update must be an object.")
    idx = update.get("idx")
    if not isinstance(idx, int) or idx < 0 or idx >= total:
        raise SystemExit(f"invalid idx: {idx}")
    category = update.get("category")
    if category not in CATEGORIES:
        raise SystemExit(f"invalid category for idx {idx}: {category}")
    priority = update.get("readingPriority")
    if priority not in PRIORITIES:
        raise SystemExit(f"invalid readingPriority for idx {idx}: {priority}")
    for key in ["topic", "reason", "classificationConfidence"]:
        if key not in update:
            raise SystemExit(f"missing {key} for idx {idx}")


def refresh_artifacts(items_path, items):
    output_dir = items_path.parent
    graph = build_graph(items)
    (output_dir / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index(items, output_dir)
    write_reading_plan(items, output_dir)
    print(f"Refreshed graph/index artifacts: {output_dir}")


def clean_text(value):
    return " ".join(str(value or "").split()).strip()


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


if __name__ == "__main__":
    main()
