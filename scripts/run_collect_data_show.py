#!/usr/bin/env python3
import argparse
import socket
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = Path("~/Documents/zhihu-knowledge").expanduser()
DEFAULT_RAW_OUTPUT = Path("~/Documents/zhihu-favorites.json").expanduser()


def main():
    parser = argparse.ArgumentParser(description="Run collect-data-show source pipelines.")
    subparsers = parser.add_subparsers(dest="source", required=True)

    zhihu = subparsers.add_parser("zhihu", help="Collect Zhihu favorites, classify them with AI, and generate a dashboard.")
    zhihu.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    zhihu.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    zhihu.add_argument("--title", default="知乎收藏知识库")
    zhihu.add_argument("--skip-collect", action="store_true", help="Use existing raw output/items instead of opening the browser.")
    zhihu.add_argument("--api-ai", action="store_true", help="Use the OpenAI API classifier. Interactive Codex sessions should normally leave this off.")
    zhihu.add_argument("--batch-size", type=int, default=25)
    zhihu.add_argument("--model", default=None)
    zhihu.add_argument("--headless", action="store_true")
    zhihu.add_argument("--channel", default=None)
    zhihu.add_argument("--no-serve", action="store_true")
    zhihu.add_argument("--port", type=int, default=8765)

    args = parser.parse_args()
    if args.source == "zhihu":
        run_zhihu(args)


def run_zhihu(args):
    output_dir = args.output_dir.expanduser().resolve()
    raw_output = args.raw_output.expanduser().resolve()
    items_path = output_dir / "items.json"

    output_dir.mkdir(parents=True, exist_ok=True)

    if args.skip_collect:
        if not items_path.exists():
            if not raw_output.exists():
                raise SystemExit(f"Missing existing data: {items_path} or {raw_output}")
            run([
                SCRIPT_DIR / "compile_zhihu_favorites.py",
                raw_output,
                "--output",
                output_dir,
            ])
    else:
        collect_command = [
            SCRIPT_DIR / "collect_zhihu_favorites.py",
            "--output",
            raw_output,
            "--compile",
            "--compile-output",
            output_dir,
        ]
        if args.headless:
            collect_command.append("--headless")
        if args.channel:
            collect_command.extend(["--channel", args.channel])
        run(collect_command)

    if not items_path.exists():
        raise SystemExit(f"Compilation did not produce items.json: {items_path}")

    if args.api_ai:
        classify_command = [
            SCRIPT_DIR / "classify_items_ai.py",
            items_path,
            "--output",
            items_path,
            "--batch-size",
            str(args.batch_size),
        ]
        if args.model:
            classify_command.extend(["--model", args.model])
        run(classify_command)
    else:
        print("Skipped external API classification. In an interactive Codex session, classify items with the active assistant model, then run refresh_zhihu_artifacts.py.")

    run([
        SCRIPT_DIR / "generate_data_viewer.py",
        items_path,
        "--output",
        output_dir,
        "--title",
        args.title,
        "--force",
    ])

    if not args.no_serve:
        port = first_free_port(args.port)
        start_server(output_dir, port)
        print(f"Dashboard: http://127.0.0.1:{port}/index.html")
    else:
        print(f"Dashboard file: {output_dir / 'index.html'}")


def run(command):
    printable = " ".join(str(part) for part in command)
    print(f"\n$ {printable}")
    process = subprocess.run([sys.executable, *map(str, command)], check=False)
    if process.returncode != 0:
        raise SystemExit(process.returncode)


def first_free_port(start):
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise SystemExit("No free localhost port found.")


def start_server(output_dir, port):
    log_path = Path("/tmp/collect-data-show-http.log")
    pid_path = Path("/tmp/collect-data-show-viewer.pid")
    log = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=output_dir,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    pid_path.write_text(str(process.pid), encoding="utf-8")
    print(f"Serving {output_dir} on 127.0.0.1:{port} (pid {process.pid}, log {log_path})")


if __name__ == "__main__":
    main()
