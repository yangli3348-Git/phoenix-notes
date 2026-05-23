#!/usr/bin/env python3
"""
📡 进程一：标题采集器（轻量常驻）
每15分钟: 轮询9源 → 去重 → DeepSeek 翻译+坐标 → 入池 titles_24h.json
"""

import subprocess, re, json, time, os, requests, threading
from datetime import datetime, timezone, timedelta

# ── 绝对路径 ──
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ── 配置 ──
INTERVAL = int(os.environ.get("COLLECTOR_INTERVAL", "900"))
FORCE_PROXY = os.environ.get("COLLECTOR_FORCE_PROXY", "").lower() in ("1", "true", "yes")
DEEPSEEK_KEY = "sk-9f7eb5c437c74b5ea22af41f230ce2b4"
PROXY_URL = "http://127.0.0.1:7890"

TITLES_FILE = os.path.join(DATA_DIR, "titles_24h.json")
SEEN_FILE = os.path.join(DATA_DIR, "seen_titles.json")
STATS_FILE = os.path.join(DATA_DIR, "collector_stats.json")

# ── 源 ──
from sources import SOURCES

if FORCE_PROXY:
    for s in SOURCES:
        s["proxy"] = True

# ── 全局状态 ──
write_lock = threading.Lock()
seen_titles = {}  # {normalized: {title, source, link, pubDate, first_seen}}
source_order = [s["name"] for s in SOURCES]  # 保持源顺序

def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)

# ── 工具函数 ──
def normalize(title):
    t = title.lower()
    t = re.sub(r'^(urgent|flash|roundup|feature|update|breaking|explainer|interview|analysis|opinion|editorial):\s*', '', t)
    t = re.sub(r'[^a-z0-9\s]', '', t)
    return re.sub(r'\s+', ' ', t).strip()

def is_within_24h(pub_date_str):
    try:
        from dateutil.parser import parse as dateparse
        t = dateparse(pub_date_str)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t > datetime.now(timezone.utc) - timedelta(hours=24)
    except:
        return False  # 解析失败默认丢弃，避免放行所有

def http_get(url, use_proxy=False):
    cmd = ["curl", "-sL", "--max-time", "12"]
    if use_proxy:
        cmd = ["curl", "-x", PROXY_URL, "-sL", "--max-time", "12"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if r.returncode != 0 or not r.stdout:
        raise Exception("empty response")
    return r.stdout

# ── 采集：新华社 JSON ──
def fetch_xinhua(src):
    kw = {}
    if FORCE_PROXY:
        kw["proxies"] = {"http": PROXY_URL, "https": PROXY_URL}
    resp = requests.get(src["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=15, **kw)
    data = resp.json()
    results = []
    for it in data.get("datasource", []):
        t = (it.get("showTitle") or "").strip()
        if not t or len(t) < 10:
            continue
        url = it.get("publishUrl", "")
        if url.startswith(".."):
            url = "https://english.news.cn" + url[2:]
        results.append({
            "title": t,
            "link": url,
            "pubDate": it.get("publishTime", ""),
            "titleImages": it.get("titleImages", []),
        })
    return results

# ── 采集：RSS ──
def fetch_rss(src):
    use_proxy = src.get("proxy", False)
    if src["name"] == "tass":
        kw = {}
        if use_proxy:
            kw["proxies"] = {"http": PROXY_URL, "https": PROXY_URL}
        resp = requests.get(src["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=15, **kw)
        html = resp.text
    else:
        html = http_get(src["url"], use_proxy=use_proxy)

    items = re.findall(r"<item[^>]*>(.*?)</item>", html, re.DOTALL)
    if not items:
        raise Exception("no items")

    titles = []
    for item in items:
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.+?)(?:\]\]>)?</title>", item)
        if not t:
            continue
        title = t.group(1).strip()
        if len(title) < 10:
            continue
        link_m = re.search(r"<link>(.+?)</link>", item)
        link = link_m.group(1).strip() if link_m else ""
        d = re.search(r"<pubDate>(.+?)</pubDate>", item) or re.search(r"<dc:date>(.+?)</dc:date>", item)
        pub_date = d.group(1).strip() if d else ""

        # 提取 RSS 中的摘要（去除 HTML 标签）
        desc_m = re.search(r"<description>(?:<!\[CDATA\[)?(.+?)(?:\]\]>)?</description>", item, re.DOTALL)
        description = ""
        images = []
        if desc_m:
            raw = desc_m.group(1)
            # 提取描述里的图片
            for img in re.findall(r'<img[^>]*src=["\']([^"\']+)["\']', raw, re.DOTALL):
                if not any(x in img.lower() for x in ['pixel', 'counter', 'tracking']):
                    images.append(img)
            # 清理 HTML 标签得到纯文本
            description = re.sub(r'<[^>]+>', ' ', raw).strip()
            description = re.sub(r'\s+', ' ', description)
            # 过滤 RT 的 "Read Full Article at RT.com" 尾巴
            description = re.sub(r'Read Full Article at .+$', '', description).strip()

        # 提取 media:content / media:thumbnail（BBC / NYT / CNN / F24）
        if not images:
            for mc in re.findall(r'<(?:media:content|media:thumbnail)[^>]*url=["\']([^"\']+)["\']', item):
                images.append(mc)

        # RT 的 content:encoded 里有完整正文
        enc_m = re.search(r"<content:encoded>(?:<!\[CDATA\[)?(.+?)(?:\]\]>)?</content:encoded>", item, re.DOTALL)
        full_text = ""
        if enc_m:
            raw = enc_m.group(1)
            # 提取所有 p 标签
            parts = []
            for p in re.findall(r'<p[^>]*>(.*?)</p>', raw, re.DOTALL):
                t2 = re.sub(r'<[^>]+>', ' ', p).strip()
                t2 = re.sub(r'\s+', ' ', t2)
                if len(t2) > 25:
                    parts.append(t2)
            full_text = " ".join(parts)

        titles.append({
            "title": title,
            "link": link,
            "pubDate": pub_date,
            "description": description,
            "images": images,
            "full_text": full_text,
        })
    return titles

# ── 去重入库 ──
def load_seen():
    global seen_titles
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            seen_titles = json.load(f)
        log(f"加载去重库: {len(seen_titles)} 条")

def save_seen():
    with write_lock:
        with open(SEEN_FILE, "w") as f:
            json.dump(seen_titles, f, ensure_ascii=False)

def deduplicate(source_name, titles_list):
    """去重，返回新增的标题列表"""
    new_entries = []
    now_ts = time.time()
    with write_lock:
        for t in titles_list:
            norm = normalize(t["title"])
            if norm in seen_titles:
                continue
            if not is_within_24h(t.get("pubDate", "")):
                continue
            entry = {
                "title": t["title"],
                "source": source_name,
                "link": t.get("link", ""),
                "pubDate": t.get("pubDate", ""),
                "titleImages": t.get("titleImages", []),
                "description": t.get("description", ""),
                "images": t.get("images", []),
                "full_text": t.get("full_text", ""),
                "first_seen": now_ts,
            }
            seen_titles[norm] = entry
            new_entries.append(entry)
    return new_entries

# ── DeepSeek 批量翻译+坐标（json_mode）──
TRANSLATE_SYSTEM = """你是新闻处理助手。用户会提供一批英文新闻标题（每条约定的编号和原文）。
你需要为每条标题：
1. 翻译为中文，限20字以内，言简意赅
2. 推断事发城市名和国家（如 HK→香港，UK→英国伦敦；若为全球性事件如科技/经济趋势填 "global"；无法确定填 "unknown"）

请严格按照以下 JSON 格式返回，不要包含其他文字：
{
  "items": [
    {"id": 1, "title_cn": "中文标题", "city": "城市名", "lat": 0.0, "lng": 0.0},
    ...
  ]
}
lat/lng 可以填 0.0（无需精确坐标）。"""


def batch_translate(new_entries, batch_size=200):
    """分批调 DeepSeek 翻译+坐标（json_mode），返回更新后的 entries"""
    results = []
    for i in range(0, len(new_entries), batch_size):
        batch = new_entries[i:i + batch_size]
        titles_text = "\n".join(f"{j+1}. {e['title']}" for j, e in enumerate(batch))

        try:
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": TRANSLATE_SYSTEM},
                        {"role": "user", "content": titles_text}
                    ],
                    "response_format": {"type": "json_object"},
                    "max_tokens": 16000,
                    "temperature": 0.3
                },
                timeout=120
            )
            body = resp.json()
            content = body["choices"][0]["message"]["content"].strip()
            log(f"  🤖 DeepSeek 翻译 {len(batch)} 条")

            # json_mode 直接解析
            try:
                data = json.loads(content)
                items = data.get("items", [])
            except (json.JSONDecodeError, KeyError):
                log(f"  ⚠️ JSON 解析失败，跳过这批")
                for e in batch:
                    e["title_cn"] = e["title"][:20]
                    e["city"] = "unknown"
                    e["lat"], e["lng"] = 0.0, 0.0
                results.extend(batch)
                continue

            parsed = {}
            for item in items:
                idx = item.get("id", -1) - 1
                if 0 <= idx < len(batch):
                    parsed[idx] = {
                        "title_cn": str(item.get("title_cn", ""))[:20],
                        "city": item.get("city", "unknown"),
                        "lat": float(item.get("lat", 0.0)),
                        "lng": float(item.get("lng", 0.0)),
                    }

            for j, e in enumerate(batch):
                if j in parsed:
                    e["title_cn"] = parsed[j]["title_cn"]
                    e["city"] = parsed[j]["city"]
                    e["lat"] = parsed[j]["lat"]
                    e["lng"] = parsed[j]["lng"]
                else:
                    e["title_cn"] = e["title"][:20]
                    e["city"] = "unknown"
                    e["lat"], e["lng"] = 0.0, 0.0
            results.extend(batch)

        except Exception as ex:
            log(f"  ❌ DeepSeek 翻译失败: {ex}")
            for e in batch:
                e["title_cn"] = e["title"][:20]
                e["city"] = "unknown"
                e["lat"], e["lng"] = 0.0, 0.0
            results.extend(batch)
    return results

# ── 出池&写文件 ──
def generate_titles_json():
    """从 seen_titles 生成 titles_24h.json（只含24h内+翻译后的）"""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp()
    titles = []
    with write_lock:
        for norm, info in seen_titles.items():
            if info.get("first_seen", 0) < cutoff:
                continue
            titles.append({
                "id": f"{info['source']}_{abs(hash(norm)) % 100000}",
                "source": info["source"],
                "title_original": info["title"],
                "title_cn": info.get("title_cn", info["title"][:20]),
                "link": info.get("link", ""),
                "pubDate": info.get("pubDate", ""),
                "first_seen": info["first_seen"],
                "city": info.get("city", "unknown"),
                "lat": info.get("lat", 0.0),
                "lng": info.get("lng", 0.0),
                "has_images": bool(info.get("titleImages") or info.get("images")),
                # RSS 预取字段（可跳过详情抓取）
                "description": info.get("description", ""),
                "images": info.get("images", []),
                "full_text": info.get("full_text", ""),
            })

    titles.sort(key=lambda x: x.get("first_seen", 0), reverse=True)

    with open(TITLES_FILE, "w") as f:
        json.dump(titles, f, ensure_ascii=False, indent=2)

    src_counts = {}
    for t in titles:
        s = t["source"]
        src_counts[s] = src_counts.get(s, 0) + 1
    return len(titles), src_counts

def save_stats(fetched, new_count, fail_count):
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pool_size": len([e for e in seen_titles.values() if e["first_seen"] > time.time() - 86400]),
        "total_fetched": fetched,
        "total_new": new_count,
        "total_fail": fail_count,
    }
    with open(STATS_FILE, "w") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

# ── 主循环 ──
def main():
    log("=" * 50)
    log(f"📡 标题采集器 v4 · {len(SOURCES)}源 · 间隔{INTERVAL}s")
    log(f"输出: {TITLES_FILE}")
    log(f"去重: {SEEN_FILE}")
    log("=" * 50)

    load_seen()

    while True:
        total_raw = 0
        total_new = 0
        total_err = 0
        all_new_entries = []

        # 1. 轮询采集
        for src in SOURCES:
            name = src["name"]
            try:
                titles = fetch_xinhua(src) if src["type"] == "xin_json" else fetch_rss(src)
                raw = len(titles)
                new_entries = deduplicate(name, titles)
                new_count = len(new_entries)
                total_raw += raw
                total_new += new_count
                all_new_entries.extend(new_entries)
                log(f"[{name:>10}] raw={raw} new={new_count}")
            except Exception as e:
                total_err += 1
                log(f"[{name:>10}] ❌ {e}")

        # 2. DeepSeek 批量翻译+坐标
        if all_new_entries:
            log(f"🤖 翻译+坐标 {len(all_new_entries)} 条新标题...")
            results = batch_translate(all_new_entries)
            # 更新 seen_titles 中的翻译结果
            with write_lock:
                for e in results:
                    norm = normalize(e["title"])
                    if norm in seen_titles:
                        seen_titles[norm]["title_cn"] = e.get("title_cn", e["title"][:20])
                        seen_titles[norm]["city"] = e.get("city", "unknown")
                        seen_titles[norm]["lat"] = e.get("lat", 0.0)
                        seen_titles[norm]["lng"] = e.get("lng", 0.0)

        # 3. 保存
        save_seen()
        pool_size, src_counts = generate_titles_json()
        save_stats(total_raw, total_new, total_err)

        src_summary = " ".join(f"{s}:{src_counts.get(s,0)}" for s in source_order if src_counts.get(s, 0))
        log(f"📊 池子: {pool_size}条 → {src_summary}")

        time.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("[终止]")
        save_seen()
        generate_titles_json()
    except Exception as e:
        log(f"[致命] {e}")
        import traceback
        traceback.print_exc()
