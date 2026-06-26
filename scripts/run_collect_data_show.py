#!/usr/bin/env python3
import argparse
import socket
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_VENV = Path("~/.local/share/collect-data-show-venv").expanduser()
DEFAULT_ZHIHU_OUTPUT_DIR = Path("~/Documents/zhihu-knowledge").expanduser()
DEFAULT_ZHIHU_RAW_OUTPUT = Path("~/Documents/zhihu-favorites.json").expanduser()
DEFAULT_BILIBILI_OUTPUT_DIR = Path("~/Documents/bilibili-knowledge").expanduser()
DEFAULT_BILIBILI_RAW_OUTPUT = Path("~/Documents/bilibili-favorites.json").expanduser()


def main():
    parser = argparse.ArgumentParser(description="Run collect-data-show source pipelines.")
    subparsers = parser.add_subparsers(dest="source", required=True)

    zhihu = subparsers.add_parser("zhihu", help="Collect Zhihu favorites, classify them with AI, and generate a dashboard.")
    zhihu.add_argument("--output-dir", type=Path, default=DEFAULT_ZHIHU_OUTPUT_DIR)
    zhihu.add_argument("--raw-output", type=Path, default=DEFAULT_ZHIHU_RAW_OUTPUT)
    zhihu.add_argument("--title", default="知乎收藏知识库")
    zhihu.add_argument("--skip-collect", action="store_true", help="Use existing raw output/items instead of opening the browser.")
    zhihu.add_argument("--api-ai", action="store_true", help="Use the OpenAI API classifier. Interactive Codex sessions should normally leave this off.")
    zhihu.add_argument("--batch-size", type=int, default=25)
    zhihu.add_argument("--model", default=None)
    zhihu.add_argument("--headless", action="store_true")
    zhihu.add_argument("--channel", default=None)
    zhihu.add_argument("--no-serve", action="store_true")
    zhihu.add_argument("--port", type=int, default=8765)

    bilibili = subparsers.add_parser("bilibili", help="Collect Bilibili favorites, compile them, and generate a dashboard.")
    bilibili.add_argument("--output-dir", type=Path, default=DEFAULT_BILIBILI_OUTPUT_DIR)
    bilibili.add_argument("--raw-output", type=Path, default=DEFAULT_BILIBILI_RAW_OUTPUT)
    bilibili.add_argument("--title", default="B 站收藏知识库")
    bilibili.add_argument("--skip-collect", action="store_true", help="Use existing raw output/items instead of opening the browser.")
    bilibili.add_argument("--api-ai", action="store_true", help="Use the OpenAI API classifier. Interactive Codex sessions should normally leave this off.")
    bilibili.add_argument("--batch-size", type=int, default=25)
    bilibili.add_argument("--model", default=None)
    bilibili.add_argument("--headless", action="store_true")
    bilibili.add_argument("--channel", default=None)
    bilibili.add_argument("--no-serve", action="store_true")
    bilibili.add_argument("--port", type=int, default=8765)

    args = parser.parse_args()
    if args.source == "zhihu":
        run_source(
            args,
            collect_script="collect_zhihu_favorites.py",
            compile_script="compile_zhihu_favorites.py",
            refresh_hint="refresh_zhihu_artifacts.py",
        )
    elif args.source == "bilibili":
        run_source(
            args,
            collect_script="collect_bilibili_favorites.py",
            compile_script="compile_bilibili_favorites.py",
            refresh_hint="compile_bilibili_favorites.py",
        )


def run_source(args, collect_script, compile_script, refresh_hint):
    output_dir = args.output_dir.expanduser().resolve()
    raw_output = args.raw_output.expanduser().resolve()
    items_path = output_dir / "items.json"

    output_dir.mkdir(parents=True, exist_ok=True)

    if args.skip_collect:
        if not items_path.exists():
            if not raw_output.exists():
                raise SystemExit(f"Missing existing data: {items_path} or {raw_output}")
            run([
                SCRIPT_DIR / compile_script,
                raw_output,
                "--output",
                output_dir,
            ])
    else:
        collect_python = ensure_playwright_python()
        collect_command = [
            SCRIPT_DIR / collect_script,
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
        run(collect_command, python=collect_python)

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
        print(f"Skipped external API classification. In an interactive Codex session, classify items with the active assistant model, then refresh artifacts with {refresh_hint}.")

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


def run(command, python=None):
    printable = " ".join(str(part) for part in command)
    print(f"\n$ {printable}")
    process = subprocess.run([python or sys.executable, *map(str, command)], check=False)
    if process.returncode != 0:
        raise SystemExit(process.returncode)


def ensure_playwright_python():
    if python_has_playwright(sys.executable):
        return sys.executable

    venv_python = DEFAULT_VENV / "bin" / "python"
    if not venv_python.exists():
        print(f"Creating browser runtime venv: {DEFAULT_VENV}")
        subprocess.run([sys.executable, "-m", "venv", str(DEFAULT_VENV)], check=True)

    if not python_has_playwright(venv_python):
        print("Installing Playwright into browser runtime venv...")
        subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([str(venv_python), "-m", "pip", "install", "playwright"], check=True)

    print("Ensuring Playwright Chromium runtime...")
    subprocess.run([str(venv_python), "-m", "playwright", "install", "chromium"], check=True)
    return str(venv_python)


def python_has_playwright(python):
    result = subprocess.run(
        [str(python), "-c", "import playwright"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


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
