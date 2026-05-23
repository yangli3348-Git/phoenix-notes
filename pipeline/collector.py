#!/usr/bin/env python3
"""
📡 进程一：标题采集器（轻量常驻）
每15分钟: 轮询9源 → 去重(DB) → DeepSeek 翻译+坐标 → 入SQLite
"""

import subprocess, re, json, time, os, requests
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

# ── 源 ──
from sources import SOURCES

if FORCE_PROXY:
    for s in SOURCES:
        s["proxy"] = True

# ── 数据库 ──
import db
source_order = [s["name"] for s in SOURCES]

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
    env = {**os.environ, "HTTP_PROXY": "", "HTTPS_PROXY": "", "http_proxy": "", "https_proxy": ""}
    if use_proxy:
        cmd = ["curl", "-x", PROXY_URL, "-sL", "--max-time", "12", "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko", url]
    else:
        cmd = ["curl", "-sL", "--max-time", "12", "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko", url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=env)
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

# ── 去重入库（基于 SQLite）──
def deduplicate(source_name, titles_list):
    """去重，返回新增的标题列表。去重和入库走 DB"""
    new_entries = []
    now_ts = time.time()
    batch_to_insert = []
    for t in titles_list:
        norm = normalize(t["title"])
        nid = f"{source_name}_{abs(hash(norm)) % 100000}"
        if db.is_seen(nid):
            continue
        if not is_within_24h(t.get("pubDate", "")):
            continue
        entry = {
            "id": nid,
            "title": t["title"],
            "title_original": t["title"],
            "source": source_name,
            "link": t.get("link", ""),
            "pubDate": t.get("pubDate", ""),
            "titleImages": t.get("titleImages", []),
            "description": t.get("description", ""),
            "images": t.get("images", []),
            "full_text": t.get("full_text", ""),
            "has_images": bool(t.get("titleImages") or t.get("images")),
            "first_seen": now_ts,
        }
        new_entries.append(entry)
        batch_to_insert.append(entry)
    if batch_to_insert:
        db.upsert_news(batch_to_insert)
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
                    "model": "deepseek-v4-flash",
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

            # json_mode 直接解析（兼容 markdown 包裹）
            content = re.sub(r'^```(?:json)?\s*', '', content.strip())
            content = re.sub(r'\s*```$', '', content)
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
    # 翻译完后同步到 DB
    db.update_translation(results)
    return results

# ── 查询（兼容旧调用）──
def generate_titles_json():
    """从 DB 获取过去24小时新闻"""
    titles = db.get_recent_24h()
    for t in titles:
        if isinstance(t.get("images"), str):
            t["images"] = json.loads(t["images"])
        t["has_images"] = bool(t.get("has_rss_images"))
    src_counts = {}
    for t in titles:
        s = t["source"]
        src_counts[s] = src_counts.get(s, 0) + 1
    return len(titles), src_counts

# ── 主循环 ──
def main():
    log("=" * 50)
    log(f"📡 标题采集器 v5 · {len(SOURCES)}源 · 间隔{INTERVAL}s")
    log(f"存储: SQLite @ {db.DB_PATH}")
    log("=" * 50)

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

        # 2. DeepSeek 批量翻译+坐标 → 自动回写 DB
        if all_new_entries:
            log(f"🤖 翻译+坐标 {len(all_new_entries)} 条新标题...")
            batch_translate(all_new_entries)

        # 3. 统计
        pool_size, src_counts = generate_titles_json()
        stats = db.get_stats()

        src_summary = " ".join(f"{s}:{src_counts.get(s,0)}" for s in source_order if src_counts.get(s, 0))
        log(f"📊 池子: {pool_size}条 | DB累计: {stats['total']}条 → {src_summary}")

        time.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("[终止]")
    except Exception as e:
        log(f"[致命] {e}")
        import traceback
        traceback.print_exc()
