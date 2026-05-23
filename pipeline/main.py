"""
🎙️ 进程二：弹窗制作器
每15分钟: 扫描 titles_24h.json 新标题 → 抓详情 → DeepSeek口播 → TTS → popup_data.json
"""

import os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetcher import fetch
from script_gen import generate
from tts import synthesize
from store import load_json, save_json

# ── 数据路径 ──
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUTPUT_DIR = os.path.join(HERE, "..", "大屏")  # popup_data.json + mp3 统一输出到大屏目录
os.makedirs(DATA_DIR, exist_ok=True)

INTERVAL = 900
MAX_POPUP = 50

TITLES_FILE = os.path.join(DATA_DIR, "titles_24h.json")
PROCESSED_FILE = os.path.join(DATA_DIR, "processed_ids.json")
POPUP_FILE = os.path.join(OUTPUT_DIR, "popup_data.json")


def load_titles():
    """读取采集器产出的 titles_24h.json"""
    return load_json(TITLES_FILE, [])


def load_processed():
    return load_json(PROCESSED_FILE, {})


def save_processed(data):
    save_json(PROCESSED_FILE, data)


def load_popup():
    return load_json(POPUP_FILE, [])


def save_popup(data):
    save_json(POPUP_FILE, data[-MAX_POPUP:])


def get_new_titles(titles, processed):
    """挑出未处理的新标题"""
    new_items = []
    for t in titles:
        tid = t.get("id", "")
        if tid not in processed:
            new_items.append(t)
    return new_items


def process_item(item, processed, popup_data):
    """处理单条：抓取→口播→TTS"""
    src = item["source"]
    tid = item["id"]
    title = item.get("title_original", item.get("title", ""))[:80]

    print(f"  📡 [{src}] {title}...")

    # 如果 RSS 已包含足够文本，直接使用，跳过详情抓取
    rss_full_text = item.get("full_text", "")
    rss_description = item.get("description", "")
    rss_images = item.get("images", [])

    # 无图不制作弹窗
    has_rss_images = len(rss_images) > 0
    has_xin_images = src == "xin-world" and item.get("has_images", False)
    if not has_rss_images and not has_xin_images:
        print(f"    ⏭️ 无配图，跳过")
        processed[tid] = True
        return None

    # 决定用哪段文本：优先 full_text，其次 description
    rss_text = rss_full_text if (rss_full_text and len(rss_full_text) >= 100) else rss_description

    if rss_text and len(rss_text) >= 100:
        detail = {
            "title": item.get("title_original", item.get("title", "")),
            "text": rss_text,
            "images": rss_images,
            "url": item.get("link", ""),
        }
        print(f"    ⚡ RSS预取({len(rss_text)}字/{len(rss_images)}图)，跳过抓详情")
    else:
        # 构造 item 给 fetcher（兼容旧格式，同时传 RSS 预取数据备用）
        fetch_item = {
            "source": src,
            "title": item.get("title_original", item.get("title", "")),
            "link": item.get("link", ""),
            "titleImages": item.get("titleImages", []),
            "description": rss_description,
            "images": rss_images,
        }

        # 抓详情
        detail = fetch(src, fetch_item)
        if not detail or len(detail.get("text", "")) < 30:
            processed[tid] = True
            return None

    # 2. DeepSeek 口播
    cn_title, script = generate(detail)
    if not script:
        processed[tid] = True
        return None

    print(f"    📰 {cn_title}")
    print(f"    🎙️ {script[:50]}...")

    # 3. TTS
    ts = datetime.now().strftime("%H%M%S")
    src_short = src.replace("-world", "")
    audio_name = f"auto_{src_short}_{ts}.mp3"
    audio_path = os.path.join(OUTPUT_DIR, audio_name)

    if synthesize(script, audio_path):
        processed[tid] = True
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

    processed[tid] = True
    return None


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎙️ 弹窗制作器 v4 启动")
    print(f"  标题数据: {TITLES_FILE}")
    print(f"  弹窗数据: {POPUP_FILE}")
    print(f"  容量上限: {MAX_POPUP}条")
    print(f"  轮询间隔: {INTERVAL}秒")

    while True:
        try:
            titles = load_titles()
            processed = load_processed()
            popup_data = load_popup()

            new_titles = get_new_titles(titles, processed)
            if not new_titles:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 无新标题, 等待...")
                time.sleep(INTERVAL)
                continue

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 📰 {len(new_titles)}条未处理")
            added = 0

            for item in new_titles:
                result = process_item(item, processed, popup_data)
                if result:
                    popup_data.append(result)
                    added += 1

                # 每处理5条存一次
                if added > 0 and added % 5 == 0:
                    save_popup(popup_data)
                    save_processed(processed)

            if added:
                save_popup(popup_data)
                save_processed(processed)
                print(f"  ✅ 新增{added}条 → popup_data.json ({len(popup_data)}条)")

            save_processed(processed)
            time.sleep(INTERVAL)

        except KeyboardInterrupt:
            save_processed(processed)
            break
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(60)


if __name__ == "__main__":
    main()
