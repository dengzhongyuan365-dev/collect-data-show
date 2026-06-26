#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_PROFILE = Path("~/.local/share/collect-data-show-bilibili-browser-profile").expanduser()
DEFAULT_OUTPUT = Path("~/Documents/bilibili-favorites.json").expanduser()
LOGIN_WINDOW_TITLE = "CODEX_BILIBILI_LOGIN_WINDOW"


COLLECT_SCRIPT = r"""
async ({ limit, delayMs }) => {
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function cleanText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function normalizeUrl(rawUrl) {
    if (!rawUrl) return "";
    try {
      const url = new URL(rawUrl, window.location.origin);
      url.hash = "";
      return url.href;
    } catch (_error) {
      return "";
    }
  }

  function normalizeCover(rawUrl) {
    const text = cleanText(rawUrl);
    if (text.startsWith("//")) return `https:${text}`;
    return text;
  }

  async function fetchBiliJson(path) {
    const response = await fetch(path, {
      method: "GET",
      credentials: "include",
      headers: {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest"
      }
    });
    if (!response.ok) {
      throw new Error(`接口请求失败：${response.status}`);
    }
    const payload = await response.json();
    if (payload && payload.code !== 0) {
      throw new Error(payload.message || `接口返回错误：${payload.code}`);
    }
    return payload;
  }

  async function getCurrentUser() {
    const payload = await fetchBiliJson("https://api.bilibili.com/x/web-interface/nav");
    const data = payload.data || {};
    if (!data.isLogin || !data.mid) {
      throw new Error("NOT_LOGGED_IN");
    }
    return {
      mid: data.mid,
      uname: cleanText(data.uname),
      face: normalizeCover(data.face)
    };
  }

  function normalizeCollection(raw) {
    const id = raw?.id || raw?.media_id || raw?.fid;
    if (!id) return null;
    return {
      id: String(id),
      title: cleanText(raw.title || raw.name || `收藏夹 ${id}`),
      description: cleanText(raw.intro || raw.description || ""),
      itemCount: raw.media_count ?? raw.count ?? 0,
      fid: raw.fid ?? null,
      attr: raw.attr ?? null,
      cover: normalizeCover(raw.cover || raw.cover_type),
      url: `https://space.bilibili.com/${raw.mid || ""}/favlist?fid=${id}`
    };
  }

  async function fetchCollections(mid) {
    const payload = await fetchBiliJson(`https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid=${encodeURIComponent(mid)}&jsonp=jsonp`);
    const rawList = payload?.data?.list || payload?.data || [];
    const collections = [];
    const seen = new Set();
    for (const raw of Array.isArray(rawList) ? rawList : []) {
      const collection = normalizeCollection(raw);
      if (collection?.id && !seen.has(collection.id)) {
        seen.add(collection.id);
        collections.push(collection);
      }
    }
    return collections;
  }

  function normalizeMedia(raw, collection) {
    const bvid = cleanText(raw.bvid || raw.bv_id || "");
    const aid = raw.id || raw.aid;
    const title = cleanText(raw.title);
    let url = normalizeUrl(raw.link || raw.uri || "");
    if (!url) {
      if (bvid) url = `https://www.bilibili.com/video/${bvid}`;
      else if (aid) url = `https://www.bilibili.com/video/av${aid}`;
    }
    if (!title || !url) return null;

    const upper = raw.upper || {};
    const cnt = raw.cnt_info || {};
    const tags = [];
    if (raw.tname) tags.push(raw.tname);
    if (raw.type_name) tags.push(raw.type_name);

    return {
      id: bvid || String(aid || url),
      title,
      url,
      author: cleanText(upper.name || raw.upperName || ""),
      upperMid: upper.mid || raw.upper_mid || null,
      summary: cleanText(raw.intro || raw.desc || ""),
      tags,
      source: "bilibili",
      sourceType: "video",
      bvid,
      aid,
      cover: normalizeCover(raw.cover || raw.pic),
      duration: raw.duration ?? null,
      pubTime: raw.pubtime ?? raw.pub_time ?? null,
      favTime: raw.fav_time ?? raw.favTime ?? null,
      playCount: cnt.play ?? raw.play ?? null,
      danmakuCount: cnt.danmaku ?? raw.danmaku ?? null,
      collectionId: collection.id,
      collectionTitle: collection.title,
      collectionUrl: collection.url,
      collectionRefs: [{
        id: collection.id,
        title: collection.title,
        url: collection.url
      }],
      collectedAt: new Date().toISOString()
    };
  }

  async function fetchCollectionItems(collection) {
    const pageSize = 20;
    let page = 1;
    let hasMore = true;
    const items = [];
    const seen = new Set();

    while (hasMore) {
      const url = `https://api.bilibili.com/x/v3/fav/resource/list?media_id=${encodeURIComponent(collection.id)}&pn=${page}&ps=${pageSize}&keyword=&order=mtime&type=0&tid=0&platform=web`;
      const payload = await fetchBiliJson(url);
      const data = payload.data || {};
      const medias = Array.isArray(data.medias) ? data.medias : [];
      for (const raw of medias) {
        const item = normalizeMedia(raw, collection);
        if (item?.url && !seen.has(item.url)) {
          seen.add(item.url);
          items.push(item);
        }
      }
      hasMore = Boolean(data.has_more) && medias.length > 0;
      page += 1;
      await wait(delayMs);
      if (items.length > limit) {
        throw new Error(`单个收藏夹超过 ${limit} 条，已停止。`);
      }
      if (page > 1000) {
        throw new Error("分页超过 1000 页，已停止。");
      }
    }
    return items;
  }

  const user = await getCurrentUser();
  const collections = await fetchCollections(user.mid);
  const items = [];
  const errors = [];

  for (const collection of collections) {
    try {
      items.push(...await fetchCollectionItems(collection));
    } catch (error) {
      errors.push({ collectionId: collection.id, collectionTitle: collection.title, message: error.message });
    }
    await wait(delayMs);
  }

  return {
    source: "bilibili",
    user,
    collectedAt: new Date().toISOString(),
    collections,
    collectionCount: collections.length,
    items,
    itemCount: items.length,
    errors
  };
}
"""


def import_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ModuleNotFoundError:
        print("缺少 Playwright。请先安装：", file=sys.stderr)
        print("  python3 -m pip install playwright", file=sys.stderr)
        print("  python3 -m playwright install chromium", file=sys.stderr)
        raise SystemExit(2)


def read_user(page):
    return page.evaluate(
        """async () => {
          try {
            const response = await fetch("https://api.bilibili.com/x/web-interface/nav", {
              credentials: "include",
              headers: { "Accept": "application/json, text/plain, */*" }
            });
            const payload = await response.json();
            const data = payload.data || {};
            return data.isLogin && data.mid ? { mid: data.mid, uname: data.uname || "" } : null;
          } catch (_error) {
            return null;
          }
        }"""
    )


def ensure_logged_in(page, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    prompted = False
    while time.monotonic() < deadline:
        user = read_user(page)
        if user and user.get("mid"):
            return user
        if not prompted:
            print("没有检测到 B 站登录态。请在打开的浏览器里登录/完成验证，检测到登录后会自动继续。")
            prompted = True
        time.sleep(3)
        try:
            page.reload(wait_until="domcontentloaded")
        except Exception:
            pass
    raise RuntimeError(f"等待 {timeout_seconds} 秒后仍未检测到 B 站登录态。")


def focus_window_by_title(title):
    if not shutil.which("xdotool"):
        return
    try:
        result = subprocess.run(["xdotool", "search", "--name", title], check=False, capture_output=True, text=True)
        window_ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not window_ids:
            return
        window_id = window_ids[-1]
        subprocess.run(["xdotool", "windowactivate", "--sync", window_id], check=False)
        subprocess.run(["xdotool", "windowsize", window_id, "1280", "900"], check=False)
        subprocess.run(["xdotool", "windowmove", window_id, "80", "60"], check=False)
    except Exception:
        return


def collect(args):
    sync_playwright = import_playwright()
    profile_dir = args.profile.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        launch_options = {
            "headless": args.headless,
            "viewport": {"width": 1280, "height": 900},
            "args": [
                "--start-normal",
                "--window-position=80,60",
                "--window-size=1280,900",
            ],
        }
        if args.executable_path:
            launch_options["executable_path"] = str(args.executable_path.expanduser().resolve())
        if args.channel:
            launch_options["channel"] = args.channel

        context = playwright.chromium.launch_persistent_context(str(profile_dir), **launch_options)
        page = context.pages[0] if context.pages else context.new_page()
        if not args.headless:
            page.goto(f"data:text/html,<title>{LOGIN_WINDOW_TITLE}</title><h1>{LOGIN_WINDOW_TITLE}</h1>", wait_until="domcontentloaded")
            time.sleep(1)
            focus_window_by_title(LOGIN_WINDOW_TITLE)
        page.goto("https://www.bilibili.com/", wait_until="domcontentloaded")
        user = ensure_logged_in(page, args.login_timeout)
        print(f"已识别 B 站用户：{user.get('uname') or user.get('mid')} ({user.get('mid')})")
        page.goto(f"https://space.bilibili.com/{user['mid']}/favlist", wait_until="domcontentloaded")
        result = page.evaluate(COLLECT_SCRIPT, {"limit": args.limit, "delayMs": args.delay_ms})
        context.close()

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Collected {result['itemCount']} items from {result['collectionCount']} collections")
    if result.get("errors"):
        print(f"Warnings: {len(result['errors'])} collections failed")
    print(f"Output: {output_path}")
    return output_path


def compile_output(input_path, output_dir):
    script_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(script_dir))
    from compile_bilibili_favorites import compile_favorites

    items, graph = compile_favorites(input_path, output_dir)
    print(f"Compiled {len(items)} items")
    print(f"Graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    print(f"Compiled output: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Collect logged-in Bilibili favorites with a browser, then optionally compile them.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSON output path.")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="Dedicated browser profile directory.")
    parser.add_argument("--compile", action="store_true", help="Compile JSON into index.md, reading-plan.md, graph.json, and items.json.")
    parser.add_argument("--compile-output", type=Path, help="Compilation output directory.")
    parser.add_argument("--headless", action="store_true", help="Run browser headless. Do not use for first login.")
    parser.add_argument("--channel", help="Playwright browser channel, e.g. chrome or msedge.")
    parser.add_argument("--executable-path", type=Path, help="Explicit Chromium/Chrome executable path.")
    parser.add_argument("--limit", type=int, default=10000, help="Safety limit per collection.")
    parser.add_argument("--delay-ms", type=int, default=250, help="Delay between API requests.")
    parser.add_argument("--login-timeout", type=int, default=300, help="Seconds to wait for manual login/captcha verification.")
    args = parser.parse_args()

    output_path = collect(args)
    if args.compile:
        compile_dir = args.compile_output.expanduser().resolve() if args.compile_output else output_path.with_name(f"{output_path.stem}-compiled")
        compile_output(output_path, compile_dir)


if __name__ == "__main__":
    main()
