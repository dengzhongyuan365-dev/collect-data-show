#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from compile_zhihu_favorites import build_graph, write_index, write_reading_plan


def main():
    parser = argparse.ArgumentParser(description="Refresh Zhihu graph and Markdown artifacts from items.json.")
    parser.add_argument("items", type=Path, help="Path to compiled/classified items.json")
    args = parser.parse_args()

    items_path = args.items.expanduser().resolve()
    if not items_path.exists():
        raise SystemExit(f"items.json not found: {items_path}")

    items = json.loads(items_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("items.json must be a JSON array.")

    output_dir = items_path.parent
    graph = build_graph(items)
    (output_dir / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index(items, output_dir)
    write_reading_plan(items, output_dir)

    print(f"Refreshed {len(items)} items")
    print(f"Graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
