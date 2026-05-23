"""
🎙️ 进程二：弹窗制作器
每15分钟: 从 SQLite 扫描未处理新闻 → 抓详情 → DeepSeek口播 → TTS → 入库+popup_data.json
"""

import os, sys, json, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetcher import fetch
from script_gen import generate
from tts import synthesize
import db

# ── 数据路径 ──
HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(HERE, "..", "大屏")
os.makedirs(OUTPUT_DIR, exist_ok=True)

INTERVAL = 900
MAX_POPUP = 50
POPUP_FILE = os.path.join(OUTPUT_DIR, "popup_data.json")


def get_new_titles():
    """从 DB 获取未处理的新闻"""
    rows = db.get_unprocessed_news()
    for r in rows:
        if isinstance(r.get("images"), str):
            r["images"] = json.loads(r["images"])
        r["title_original"] = r.get("title_original", "")
        r["title_cn"] = r.get("title_cn", "")
        r["source"] = r.get("source", "")
        r["link"] = r.get("link", "")
        r["has_images"] = bool(r.get("has_rss_images"))
        r["description"] = r.get("description", "")
        r["full_text"] = r.get("full_text", "")
    return rows


def load_popup():
    """读取 popup_data.json"""
    if os.path.exists(POPUP_FILE):
        with open(POPUP_FILE) as f:
            return json.load(f)
    return []


def save_popup(data):
    """保存 popup_data.json"""
    with open(POPUP_FILE, 'w') as f:
        json.dump(data[-MAX_POPUP:], f, ensure_ascii=False, indent=2)


def process_item(item, popup_data):
    """处理单条：抓取→口播→TTS"""
    src = item.get("source", "")
    tid = item.get("id", "")
    title = item.get("title_original", item.get("title", ""))[:80]

    print(f"  📡 [{src}] {title}...")

    # 如果能用RSS数据跳过详情抓取，就跳过。否则抓详情页拿文/图。
    rss_full_text = item.get("full_text", "")
    rss_description = item.get("description", "")
    rss_images = item.get("images", [])

    # 选择RSS文本: 优先 full_text，其次 description
    rss_text = rss_full_text if (rss_full_text and len(rss_full_text) >= 100) else rss_description
    has_rss_text = rss_text and len(rss_text) >= 100
    has_rss_images = len(rss_images) > 0
    has_xin_images = src == "xin-world" and item.get("has_images", False)

    # 新华社：RSS无图就不抓详情
    if src == "xin-world" and not has_xin_images:
        print(f"    ⏭️ 新华社无配图，跳过")
        db.mark_processed(tid)
        return None

    if has_rss_text and has_rss_images:
        # RSS 已有文字+图片 → 跳过详情抓取
        detail = {
            "title": item.get("title_original", item.get("title", "")),
            "text": rss_text,
            "images": rss_images,
            "url": item.get("link", ""),
        }
        print(f"    ⚡ RSS预取({len(rss_text)}字/{len(rss_images)}图)，跳过详情")
    elif has_rss_text and not has_rss_images and src != "xin-world":
        # RSS有文没图 → 抓详情页取图（DW/TASS/AJ这种情况）
        print(f"    🔍 RSS有文无图，抓详情页取图...")
        fetch_item = {"source": src, "title": item.get("title_original", item.get("title", "")), "link": item.get("link", ""), "titleImages": [], "description": rss_description, "images": []}
        detail = fetch(src, fetch_item)
        if detail and detail.get("images"):
            # 用RSS文字 + 详情页图片
            detail["text"] = rss_text
            print(f"    ✅ 从详情页获得{len(detail['images'])}张图")
        elif detail and len(detail.get("text", "")) >= 30:
            print(f"    ⚠️ 详情页也无图，用纯文字")
        else:
            print(f"    ⏭️ 详情页无内容，跳过")
            db.mark_processed(tid)
            return None
    else:
        # RSS 无文（新华社/RSS极短）→ 抓详情页拿文+图
        fetch_item = {
            "source": src,
            "title": item.get("title_original", item.get("title", "")),
            "link": item.get("link", ""),
            "titleImages": item.get("titleImages", []),
            "description": rss_description,
            "images": rss_images,
        }
        detail = fetch(src, fetch_item)
        if not detail or len(detail.get("text", "")) < 30:
            db.mark_processed(tid)
            return None

    # 无图不制作弹窗
    if not detail.get("images"):
        print(f"    ⏭️ 无配图，跳过")
        db.mark_processed(tid)
        return None

    # 2. DeepSeek 口播
    cn_title, script = generate(detail)
    if not script:
        db.mark_processed(tid)
        return None

    print(f"    📰 {cn_title}")
    print(f"    🎙️ {script[:50]}...")

    # 3. TTS
    ts = datetime.now().strftime("%H%M%S")
    src_short = src.replace("-world", "")
    audio_name = f"auto_{src_short}_{ts}.mp3"
    audio_path = os.path.join(OUTPUT_DIR, audio_name)

    if synthesize(script, audio_path):
        db.mark_processed(tid)
        return {
            "id": f"{src_short}_{ts}",
            "source": src_short,
            "title": cn_title,
            "script": script,
            "audio": audio_name,
            "images": detail.get("images", []),
            "url": detail.get("url", ""),
            "time": datetime.now(timezone.utc).isoformat(),
        }

    db.mark_processed(tid)
    return None


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎙️ 弹窗制作器 v5 启动")
    print(f"  存储: SQLite @ {db.DB_PATH}")
    print(f"  弹窗数据: {POPUP_FILE}")
    print(f"  容量上限: {MAX_POPUP}条")
    print(f"  轮询间隔: {INTERVAL}秒")

    while True:
        try:
            new_titles = get_new_titles()
            popup_data = load_popup()

            if not new_titles:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 无新标题, 等待...")
                time.sleep(INTERVAL)
                continue

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 📰 {len(new_titles)}条未处理")
            added = 0

            for item in new_titles:
                result = process_item(item, popup_data)
                if result:
                    result["news_id"] = item["id"]
                    popup_data.append(result)
                    db.insert_popup(result)
                    added += 1

                if added > 0 and added % 5 == 0:
                    save_popup(popup_data)

            if added:
                save_popup(popup_data)
                print(f"  ✅ 新增{added}条 → popup_data.json ({len(popup_data)}条)")

            time.sleep(INTERVAL)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(60)


if __name__ == "__main__":
    main()
