#!/usr/bin/env python3
import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


CATEGORIES = [
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
]


SYSTEM_PROMPT = """你是一个私人知识库的信息架构师。任务是给收藏条目重新分类。

分类原则：
1. 主要根据标题判断，摘要用于辅助，不要被摘要里的偶然词误导。
2. 技术文章里出现“历史、哲学、设计”等词时，通常仍归入“AI 与技术”，除非主题真的是历史文化或哲学。
3. “设计”只有在产品、交互、用户体验、视觉、运营方案语境下才归入“产品与设计”；软件架构/系统设计归入“AI 与技术”。
4. Linux、C++、编程语言、网络、数据库、内核、开源项目、Agent、Prompt、Claude Code、Cursor、AI 编程都归入“AI 与技术”。
5. App、效率工具、浏览器、文件管理、系统软件、素材工具等偏使用工具的内容归入“软件与工具”。
6. 职场、面试、简历、学习路线、教育、考试归入“职业与教育”。
7. 输出必须覆盖输入里的每一条，不要新增不存在的条目。
"""


SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "topic": {"type": "string"},
                    "concepts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 8,
                    },
                    "readingPriority": {"type": "string", "enum": ["精读", "略读", "待判断"]},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["idx", "category", "topic", "concepts", "readingPriority", "reason", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def main():
    parser = argparse.ArgumentParser(description="Classify knowledge items with an OpenAI model.")
    parser.add_argument("input", type=Path, help="Input items.json")
    parser.add_argument("--output", "-o", type=Path, help="Output JSON path. Defaults to overwriting input.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.4-mini"))
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=0.3, help="Seconds between requests.")
    parser.add_argument("--dry-run", action="store_true", help="Print request preview without calling the API.")
    parser.add_argument("--no-refresh-artifacts", action="store_true", help="Do not rewrite graph.json, index.md, or reading-plan.md beside items.json.")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        raise SystemExit("OPENAI_API_KEY is required unless --dry-run is used.")

    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve() if args.output else input_path
    items = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("Input must be a JSON array of items.")

    for start in range(0, len(items), args.batch_size):
        batch = items[start:start + args.batch_size]
        payload = build_batch_payload(batch, start)
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2)[:3000])
            return
        print(f"Classifying {start + 1}-{start + len(batch)} / {len(items)}")
        try:
            result = classify_batch(api_key, args.model, payload)
        except Exception as error:
            raise SystemExit(f"AI 分类失败：{format_error(error)}") from error
        merge_results(items, result)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(args.sleep)

    if not args.no_refresh_artifacts:
        refresh_compiled_artifacts(output_path, items)
    print(f"Wrote {len(items)} classified items: {output_path}")


def build_batch_payload(batch, offset):
    entries = []
    for index, item in enumerate(batch, start=offset):
        entries.append({
            "idx": index,
            "title": item.get("title", ""),
            "author": item.get("author", ""),
            "summary": truncate(item.get("summary", ""), 520),
            "collections": item.get("collections", []),
            "oldCategory": item.get("category", ""),
            "oldConcepts": item.get("concepts", []),
        })
    return {
        "categories": CATEGORIES,
        "items": entries,
    }


def classify_batch(api_key, model, payload):
    user_prompt = "请按规则给下面条目分类，返回 JSON。输入：\n" + json.dumps(payload, ensure_ascii=False)
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "reasoning": {"effort": "low"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "item_classification_batch",
                "schema": SCHEMA,
                "strict": True,
            }
        },
    }
    try:
        response = post_response(api_key, body)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if error.code != 400:
            raise RuntimeError(f"OpenAI API error {error.code}: {detail}") from error
        # Some models or accounts may reject structured-output fields. Fall back to JSON-only prompting.
        fallback_body = {
            "model": model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT + "\n只输出一个 JSON 对象，格式为 {\"items\": [...]}。"},
                {"role": "user", "content": user_prompt},
            ],
        }
        response = post_response(api_key, fallback_body)

    text = extract_response_text(response)
    return json.loads(extract_json_object(text))


def post_response(api_key, body):
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def format_error(error):
    if isinstance(error, urllib.error.HTTPError):
        try:
            detail = error.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(error)
        return f"OpenAI API 返回 HTTP {error.code}: {detail[:800]}"
    if isinstance(error, urllib.error.URLError):
        return f"无法连接 OpenAI API：{error.reason}"
    return str(error)


def extract_response_text(response):
    if response.get("output_text"):
        return response["output_text"]
    parts = []
    for output in response.get("output", []):
        for content in output.get("content", []):
            text = content.get("text")
            if text:
                parts.append(text)
    return "\n".join(parts)


def extract_json_object(text):
    text = text.strip()
    if text.startswith("{"):
        return text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output: {text[:500]}")
    return match.group(0)


def merge_results(items, result):
    by_idx = {entry["idx"]: entry for entry in result.get("items", []) if isinstance(entry.get("idx"), int)}
    for idx, update in by_idx.items():
        if idx < 0 or idx >= len(items):
            continue
        item = items[idx]
        item["category"] = update["category"]
        item["topic"] = update["topic"]
        item["concepts"] = unique_list(update.get("concepts", []))
        item["readingPriority"] = update["readingPriority"]
        item["reason"] = update["reason"]
        item["classificationConfidence"] = update["confidence"]
        item["classificationMethod"] = "ai"


def refresh_compiled_artifacts(output_path, items):
    if output_path.name != "items.json":
        return
    try:
        from compile_zhihu_favorites import build_graph, write_index, write_reading_plan
    except Exception as error:
        print(f"Skipped refreshing companion artifacts: {error}")
        return

    output_dir = output_path.parent
    graph = build_graph(items)
    (output_dir / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index(items, output_dir)
    write_reading_plan(items, output_dir)
    print(f"Refreshed graph/index artifacts: {output_dir}")


def unique_list(values):
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def truncate(value, max_length):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_length]


if __name__ == "__main__":
    main()
