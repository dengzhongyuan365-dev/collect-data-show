#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_PROFILE = Path("~/.local/share/zhihu-knowledge-browser-profile").expanduser()
DEFAULT_OUTPUT = Path("~/Documents/zhihu-favorites.json").expanduser()
LOGIN_WINDOW_TITLE = "CODEX_ZHIHU_LOGIN_WINDOW"


COLLECT_SCRIPT = r"""
async ({ limit, delayMs }) => {
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function cleanText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function getInitialState() {
    const raw = document.querySelector("#js-initialData")?.textContent;
    if (!raw) return null;
    try {
      return JSON.parse(raw).initialState || null;
    } catch (_error) {
      return null;
    }
  }

  function getCurrentUserToken() {
    const state = getInitialState();
    const currentUser = state?.currentUser || "";
    const users = state?.entities?.users || {};
    const user = currentUser ? users[currentUser] : null;
    const token = cleanText(user?.urlToken || user?.url_token || user?.id || currentUser);
    return token && token !== "guest" ? token : "";
  }

  function normalizeApiRequestUrl(rawUrl) {
    if (!rawUrl) return "";
    try {
      const url = new URL(rawUrl, window.location.origin);
      if (url.hostname.endsWith("zhihu.com")) {
        return `${url.pathname}${url.search}`;
      }
    } catch (_error) {
      return rawUrl;
    }
    return rawUrl;
  }

  async function fetchZhihuJson(url) {
    const response = await fetch(normalizeApiRequestUrl(url), {
      method: "GET",
      credentials: "include",
      headers: {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "fetch"
      }
    });
    if (!response.ok) {
      throw new Error(`接口请求失败：${response.status}`);
    }
    const payload = await response.json();
    if (payload?.error) {
      throw new Error(payload.error.message || "接口返回错误。");
    }
    return payload;
  }

  function normalizeCollection(rawCollection) {
    const id = String(rawCollection?.id || rawCollection?.collection || rawCollection?.collectionId || "");
    if (!id) return null;
    const title = cleanText(rawCollection.title || rawCollection.name || "");
    return {
      id,
      title: title || `收藏夹 ${id}`,
      description: cleanText(rawCollection.description || ""),
      itemCount: rawCollection.itemCount ?? rawCollection.item_count ?? rawCollection.answerCount ?? rawCollection.answer_count ?? 0,
      followerCount: rawCollection.followerCount ?? rawCollection.follower_count ?? 0,
      updatedTime: rawCollection.updatedTime ?? rawCollection.updated_time ?? null,
      createdTime: rawCollection.createdTime ?? rawCollection.created_time ?? null,
      url: `https://www.zhihu.com/collection/${id}`
    };
  }

  function normalizeUrl(rawHref) {
    try {
      const url = new URL(rawHref, window.location.origin);
      url.hash = "";
      url.search = "";
      return url.href.replace(/\/$/, "");
    } catch (_error) {
      return "";
    }
  }

  function stripHtml(text) {
    return cleanText(String(text || "").replace(/<[^>]*>/g, " "));
  }

  function normalizeApiUrl(content, type, id, question) {
    const rawUrl = content.url || content.originalUrl || content.externalUrl || "";
    if (rawUrl && !rawUrl.includes("api.zhihu.com")) {
      return normalizeUrl(rawUrl);
    }
    if (type === "answer" && id) {
      const questionId = question.id || content.questionId || content.question_id;
      return questionId ? `https://www.zhihu.com/question/${questionId}/answer/${id}` : `https://www.zhihu.com/answer/${id}`;
    }
    if (type === "article" && id) return `https://zhuanlan.zhihu.com/p/${id}`;
    if (type === "pin" && id) return `https://www.zhihu.com/pin/${id}`;
    if (type === "zvideo" && id) return `https://www.zhihu.com/zvideo/${id}`;
    return "";
  }

  function normalizeApiItem(rawItem, collection) {
    const content = rawItem?.content || rawItem;
    if (!content || typeof content !== "object") return null;

    const type = content.type || rawItem?.type || "";
    const id = content.id || content.token || rawItem?.id || "";
    const question = content.question || {};
    const author = content.author || rawItem?.author || {};
    const title = cleanText(
      content.title ||
      content.headline ||
      question.title ||
      content.excerptTitle ||
      content.excerpt ||
      rawItem?.title ||
      ""
    );
    const url = normalizeApiUrl(content, type, id, question);
    if (!url || !title) return null;

    return {
      id: url,
      title,
      url,
      author: cleanText(author.name || author.urlToken || ""),
      excerpt: stripHtml(content.excerpt || content.excerptContent || content.content || rawItem?.excerpt || ""),
      sourceType: type,
      voteupCount: content.voteupCount ?? content.voteup_count ?? null,
      commentCount: content.commentCount ?? content.comment_count ?? null,
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

  async function fetchUserCollections(userToken) {
    const include = [
      "data[*].updated_time",
      "answer_count",
      "follower_count",
      "creator",
      "description",
      "is_following",
      "comment_count",
      "created_time",
      "data[*].creator.kvip_info",
      "data[*].creator.vip_info"
    ].join(",");
    const pageLimit = 20;
    let offset = 0;
    let nextUrl = "";
    let isEnd = false;
    const collections = [];
    const seen = new Set();

    while (!isEnd) {
      const url = nextUrl || `/api/v4/people/${encodeURIComponent(userToken)}/collections?include=${encodeURIComponent(include)}&offset=${offset}&limit=${pageLimit}`;
      const payload = await fetchZhihuJson(url);
      const pageItems = Array.isArray(payload.data) ? payload.data : [];
      for (const rawCollection of pageItems) {
        const collection = normalizeCollection(rawCollection);
        if (collection?.id && !seen.has(collection.id)) {
          seen.add(collection.id);
          collections.push(collection);
        }
      }
      const paging = payload.paging || {};
      nextUrl = normalizeApiRequestUrl(paging.next || "");
      isEnd = Boolean(paging.is_end || paging.isEnd) || pageItems.length === 0 || (!nextUrl && pageItems.length < pageLimit);
      offset += pageLimit;
      await wait(delayMs);
      if (collections.length > 500) throw new Error("收藏夹数量超过 500，已停止。");
    }
    return collections;
  }

  async function fetchCollectionItems(collection) {
    const pageLimit = 20;
    let offset = 0;
    let isEnd = false;
    const items = [];
    const seen = new Set();

    while (!isEnd) {
      const payload = await fetchZhihuJson(`/api/v4/collections/${collection.id}/items?offset=${offset}&limit=${pageLimit}`);
      const pageItems = Array.isArray(payload.data) ? payload.data : [];
      for (const rawItem of pageItems) {
        const item = normalizeApiItem(rawItem, collection);
        if (item?.url && !seen.has(item.url)) {
          seen.add(item.url);
          items.push(item);
        }
      }
      const paging = payload.paging || {};
      isEnd = Boolean(paging.is_end || paging.isEnd) || pageItems.length === 0;
      offset += pageLimit;
      await wait(delayMs);
      if (items.length > limit) throw new Error(`单个收藏夹超过 ${limit} 条，已停止。`);
    }
    return items;
  }

  const userToken = getCurrentUserToken();
  if (!userToken) {
    throw new Error("NOT_LOGGED_IN");
  }

  const collections = await fetchUserCollections(userToken);
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
    source: "zhihu",
    userToken,
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


def read_user_token(page):
    return page.evaluate(
        """() => {
          const raw = document.querySelector("#js-initialData")?.textContent;
          if (!raw) return "";
          try {
            const state = JSON.parse(raw).initialState || {};
            const currentUser = state.currentUser || "";
            const users = state.entities?.users || {};
            const user = currentUser ? users[currentUser] : null;
            const token = user?.urlToken || user?.url_token || user?.id || currentUser;
            return token && token !== "guest" ? token : "";
          } catch (_error) {
            return "";
          }
        }"""
    )


def ensure_logged_in(page, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    prompted = False
    while time.monotonic() < deadline:
        token = read_user_token(page)
        if token:
            return token
        if not prompted:
            print("没有检测到知乎登录态。请在打开的浏览器里登录/完成验证，检测到登录后会自动继续。")
            prompted = True
        time.sleep(3)
        try:
            page.reload(wait_until="domcontentloaded")
        except Exception:
            pass
    raise RuntimeError(f"等待 {timeout_seconds} 秒后仍未检测到知乎登录态。")


def focus_window_by_title(title):
    if not shutil.which("xdotool"):
        return
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", title],
            check=False,
            capture_output=True,
            text=True,
        )
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
            page.goto(
                f"data:text/html,<title>{LOGIN_WINDOW_TITLE}</title><h1>{LOGIN_WINDOW_TITLE}</h1>",
                wait_until="domcontentloaded",
            )
            time.sleep(1)
            focus_window_by_title(LOGIN_WINDOW_TITLE)
        page.goto("https://www.zhihu.com/", wait_until="domcontentloaded")
        token = ensure_logged_in(page, args.login_timeout)
        print(f"已识别知乎用户：{token}")
        page.goto("https://www.zhihu.com/collections/mine", wait_until="domcontentloaded")
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
    from compile_zhihu_favorites import compile_favorites

    items, graph = compile_favorites(input_path, output_dir)
    print(f"Compiled {len(items)} items")
    print(f"Graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    print(f"Compiled output: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Collect logged-in Zhihu favorites with a browser, then optionally compile them.")
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
