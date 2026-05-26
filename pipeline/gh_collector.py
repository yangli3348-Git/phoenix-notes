#!/usr/bin/env python3
"""
📡 GitHub Actions 采集器 — 纯采集，不做翻译

学习 daily-digest:
  - feedparser 统一解析 RSS/Atom
  - ThreadPoolExecutor 并行采集
  - 指数退避重试
  - 垃圾标题过滤
  - bozo 容错
  - published_parsed 时间过滤

输出: pipeline/data/latest_news.json
"""

import json, os, time, re, hashlib, html as html_lib
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import feedparser
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "latest_news.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ── 配置 ──
MAX_AGE_HOURS = 24          # 只收 24h 内的新闻
PER_SOURCE_LIMIT = 10       # 每个源最多收几条
PARALLEL_TIMEOUT = 60       # 并行采集总超时（秒）
RETRY_ATTEMPTS = 3          # 单个源重试次数
RETRY_BASE_DELAY = 1.5      # 基础重试间隔

# ── 源配置 ──
# type: "rss" → feedparser 通用，“xin_json” → 新华社专用
SOURCES = [
    {"name": "xin-world",  "label": "新华社",  "type": "xin_json",
     "url": "https://english.news.cn/world/ds_7718692eb4e54a328c7913da6f673e4b.json"},
    {"name": "bbc",        "label": "BBC",     "type": "rss",
     "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "cnn",        "label": "CNN",     "type": "rss",
     "url": "http://rss.cnn.com/rss/edition.rss"},
    {"name": "tass",       "label": "塔斯社",  "type": "rss",
     "url": "https://tass.com/rss/v2.xml"},
    {"name": "dw",         "label": "德国之声","type": "rss",
     "url": "https://rss.dw.com/rdf/rss-en-all"},
    {"name": "f24",        "label": "法国24",  "type": "rss",
     "url": "https://www.france24.com/en/rss"},
    {"name": "aj",         "label": "半岛电视台","type": "rss",
     "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "reddit",     "label": "Reddit",   "type": "reddit_json",
     "url": "https://www.reddit.com/r/worldnews/hot.json?limit=25"},
    {"name": "googlenews", "label": "Google新闻","type": "rss",
     "url": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"},
]

# ── 工具 ──
def log(tag: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"{ts} [{tag:<6}] {msg}", flush=True)

def normalize(title: str) -> str:
    """规范化标题用于去重"""
    t = title.lower()
    # 去前缀 (Breaking, Exclusive 等)
    t = re.sub(r'^(urgent|flash|roundup|feature|update|breaking|exclusive|explainer|interview|analysis|opinion|editorial):\s*', '', t)
    t = re.sub(r'[^a-z0-9\s]', '', t)
    return re.sub(r'\s+', ' ', t).strip()

def title_hash(title: str) -> str:
    """标题哈希 → 短 ID"""
    n = normalize(title)
    return hashlib.md5(n.encode()).hexdigest()[:12]

def is_within_hours(pub_parsed, max_hours: int = MAX_AGE_HOURS) -> bool:
    """feedparser 的 published_parsed struct_time → 判断是否在 max_hours 内"""
    if pub_parsed is None:
        return True  # 无日期默认保留
    try:
        t = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
        return t > datetime.now(timezone.utc) - timedelta(hours=max_hours)
    except (ValueError, OverflowError):
        return True

def strip_html(raw: str, max_len: int = 300) -> str:
    """去 HTML 标签，截断"""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html_lib.unescape(text)
    text = " ".join(text.split())
    return text[:max_len]

# ── 垃圾标题过滤（学 daily-digest）──
JUNK_TITLE_FRAGMENTS = (
    "latest news today",
    "breaking news",
    "top headlines",
    "live updates",
    "live news",
    "top news stories",
    "news today",
    "today's news",
    "today news",
    "latest updates",
    "all news",
    "news live",
    "horoscope",
    "horoscopes today",
    "mock draft",
    "full broadcast",
)

def is_junk_title(title: str) -> bool:
    t = title.lower()
    return any(frag in t for frag in JUNK_TITLE_FRAGMENTS)

# ── 重试（学 daily-digest 指数退避）──
def retry(fn, attempts=RETRY_ATTEMPTS, base_delay=RETRY_BASE_DELAY):
    last_exc = RuntimeError("no attempts made")
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                delay = base_delay * (2 ** attempt)
                log("RETRY", f"  attempt {attempt+1}/{attempts} in {delay:.1f}s — {exc}")
                time.sleep(delay)
    raise last_exc

# ── 采集：新华社 JSON ──
def fetch_xinhua(src: dict) -> list[dict]:
    resp = requests.get(src["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for it in data.get("datasource", []):
        title = (it.get("showTitle") or "").strip()
        if not title or len(title) < 10 or is_junk_title(title):
            continue
        url = it.get("publishUrl", "")
        if url.startswith(".."):
            url = "https://english.news.cn" + url[2:]
        pub_date = it.get("publishTime", "")
        images = it.get("titleImages", [])
        results.append({
            "title": title,
            "link": url,
            "pubDate": pub_date,
            "images": images,
            "description": "",
            "source_name": src["name"],
            "source_label": src["label"],
        })
        if len(results) >= PER_SOURCE_LIMIT:
            break
    return results

# ── 采集：Reddit JSON API ──
def fetch_reddit(src: dict) -> list[dict]:
    """Reddit JSON API — post['url'] = 新闻原文链接，可用于去重"""
    resp = requests.get(src["url"], headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for child in data.get("data", {}).get("children", []):
        post = child["data"]
        title = (post.get("title") or "").strip()
        # 跳过置顶帖/自贴（Live Thread / Discussion Thread）
        if not title or len(title) < 10 or is_junk_title(title):
            continue
        if post.get("stickied") or post.get("is_self"):
            continue
        # 原文链接
        news_url = (post.get("url") or "").strip()
        # 跳过指向 reddit 内部的链接
        if "reddit.com" in news_url or "redd.it" in news_url:
            continue
        # 时间
        created = post.get("created_utc", 0)
        pub_date_str = datetime.fromtimestamp(created, tz=timezone.utc).isoformat() if created else ""
        # 来自哪个域名
        domain = post.get("domain", "")
        desc = f"via {domain}" if domain else ""

        results.append({
            "title": title,
            "link": news_url,
            "pubDate": pub_date_str,
            "images": [],
            "description": desc,
            "source_name": src["name"],
            "source_label": src["label"],
        })
        if len(results) >= PER_SOURCE_LIMIT:
            break
    return results

# ── 采集：通用 RSS/Atom（feedparser）──
def fetch_rss(src: dict) -> list[dict]:
    d = feedparser.parse(src["url"], agent="Mozilla/5.0 (digest-bot/1.0)")
    # bozo 容错：解析错误但有 entry 就继续用
    if d.get("bozo") and not d.get("entries"):
        raise Exception(f"unparseable: {d.get('bozo_exception')}")

    results = []
    for entry in d.entries:
        if len(results) >= PER_SOURCE_LIMIT:
            break

        # 时间过滤
        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub and not is_within_hours(pub):
            continue

        title = (entry.get("title") or "").strip()
        if not title or len(title) < 10 or is_junk_title(title):
            continue

        # Reddit 标题前缀过滤（"r/worldnews - ..."）
        if src["name"] == "reddit" and title.lower().startswith("r/"):
            continue

        link = (entry.get("link") or "").strip()

        # 取 pubDate 字符串
        pub_date_str = ""
        if pub:
            try:
                pub_date_str = datetime(*pub[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pub_date_str = entry.get("published", "") or entry.get("updated", "")

        # 摘要/描述
        desc = strip_html(
            entry.get("summary", "")
            or (entry.get("content") or [{}])[0].get("value", "")
            or ""
        )

        # 图片：media_content 或 links 里的 image
        images = []
        media = entry.get("media_content", []) or []
        for m in media:
            url = m.get("url", "")
            if url and not any(x in url.lower() for x in ['pixel', 'counter', 'tracking']):
                images.append(url)
        if not images:
            for lnk in entry.get("links", []) or []:
                if lnk.get("rel") == "enclosure" or "image" in lnk.get("type", ""):
                    url = lnk.get("href", "")
                    if url:
                        images.append(url)

        results.append({
            "title": title,
            "pubDate": pub_date_str,
            "images": images,
            "description": desc[:500],
            "source_name": src["name"],
            "source_label": src["label"],
        })

    return results

# ── 主采集函数：单源 ──
def fetch_source(src: dict) -> tuple[str, list[dict]]:
    """返回 (source_label, items)"""
    name = src["name"]
    try:
        if src["type"] == "xin_json":
            items = retry(lambda: fetch_xinhua(src))
        elif src["type"] == "reddit_json":
            items = retry(lambda: fetch_reddit(src))
        else:
            items = retry(lambda: fetch_rss(src))
        log("FETCH", f"{src['label']:>8} → {len(items)} 条")
        return name, items
    except Exception as e:
        log("ERROR", f"{src['label']:>8} ✗ {e}")
        return name, []

# ── 并行采集 ──
def collect_all() -> list[dict]:
    """并行抓所有源，返回去重后的条目列表"""
    results: list[dict] = []
    seen_hashes: set[str] = set()
    now_ts = time.time()

    # 并行拉（每个源一个线程）
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        futures = {pool.submit(fetch_source, s): s["name"] for s in SOURCES}
        for future in as_completed(futures, timeout=PARALLEL_TIMEOUT):
            try:
                _, items = future.result(timeout=30)
                for item in items:
                    h = title_hash(item["title"])
                    if h in seen_hashes:
                        continue
                    seen_hashes.add(h)
                    item["id"] = f"{item['source_name']}_{h}"
                    item["collected_at"] = now_ts
                    results.append(item)
            except Exception as e:
                log("WARN", f"  future error: {e}")

    # 按采集时间排序
    results.sort(key=lambda x: x.get("collected_at", 0), reverse=True)
    log("DONE", f"共 {len(results)} 条 (去重后)，来自 {len(SOURCES)} 个源")
    return results

# ── 输出 ──
def write_output(items: list[dict]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log("WRITE", f"→ {OUTPUT_FILE} ({len(items)} 条)")

def main():
    log("START", f"GitHub Actions 采集器 · {len(SOURCES)}源 · {MAX_AGE_HOURS}h时效")
    start = time.time()
    items = collect_all()
    write_output(items)
    elapsed = time.time() - start
    log("END", f"耗时 {elapsed:.1f}s")

    # 输出源统计
    src_counts: dict[str, int] = {}
    for item in items:
        s = item["source_label"]
        src_counts[s] = src_counts.get(s, 0) + 1
    summary = " ".join(f"{k}:{v}" for k, v in src_counts.items())
    log("STATS", summary)

if __name__ == "__main__":
    main()
