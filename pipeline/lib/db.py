"""
数据库层 — SQLite 替代 JSON 文件存储
"""
import sqlite3, json, os, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "..", "data", "news.db")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS news_raw (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title_original TEXT NOT NULL,
            title_cn TEXT DEFAULT '',
            link TEXT DEFAULT '',
            pub_date TEXT DEFAULT '',
            description TEXT DEFAULT '',
            images TEXT DEFAULT '[]',
            full_text TEXT DEFAULT '',
            city TEXT DEFAULT 'unknown',
            lat REAL DEFAULT 0.0,
            lng REAL DEFAULT 0.0,
            has_rss_images INTEGER DEFAULT 0,
            collected_at REAL NOT NULL,
            translated_at REAL DEFAULT 0.0,
            is_processed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS popup (
            id TEXT PRIMARY KEY,
            news_id TEXT NOT NULL,
            source TEXT NOT NULL,
            title_cn TEXT NOT NULL,
            script TEXT NOT NULL,
            audio_path TEXT DEFAULT '',
            images TEXT DEFAULT '[]',
            url TEXT DEFAULT '',
            created_at REAL NOT NULL,
            FOREIGN KEY (news_id) REFERENCES news_raw(id)
        );

        CREATE TABLE IF NOT EXISTS seen_titles (
            normalized TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            first_seen REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_news_source ON news_raw(source);
        CREATE INDEX IF NOT EXISTS idx_news_collected ON news_raw(collected_at);
        CREATE INDEX IF NOT EXISTS idx_news_processed ON news_raw(is_processed);
        CREATE INDEX IF NOT EXISTS idx_popup_created ON popup(created_at);
    """)
    conn.commit()
    conn.close()

# ── News Raw 操作 ──

def upsert_news(news_list):
    """批量插入/更新新闻（以 id 为主键，重复则更新）"""
    conn = get_db()
    now = time.time()
    for n in news_list:
        conn.execute("""
            INSERT OR REPLACE INTO news_raw 
            (id, source, title_original, title_cn, link, pub_date, description, 
             images, full_text, city, lat, lng, has_rss_images, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            n["id"], n["source"], n["title_original"], n.get("title_cn", ""),
            n.get("link", ""), n.get("pubDate", ""), n.get("description", ""),
            json.dumps(n.get("images", [])), n.get("full_text", ""),
            n.get("city", "unknown"), n.get("lat", 0.0), n.get("lng", 0.0),
            1 if n.get("images") or n.get("has_images") else 0,
            n.get("first_seen", now)
        ))
    conn.commit()
    conn.close()

def update_translation(batch):
    """批量更新翻译结果"""
    conn = get_db()
    now = time.time()
    for e in batch:
        conn.execute("""
            UPDATE news_raw SET title_cn=?, city=?, lat=?, lng=?, translated_at=?
            WHERE id=?
        """, (e.get("title_cn", ""), e.get("city", "unknown"), 
              e.get("lat", 0.0), e.get("lng", 0.0), now, e["id"]))
    conn.commit()
    conn.close()

def get_unprocessed_news(source=None, min_collected=None):
    """获取未处理的新闻（可用于弹窗制作）"""
    conn = get_db()
    sql = "SELECT * FROM news_raw WHERE is_processed=0"
    params = []
    if source:
        sql += " AND source=?"
        params.append(source)
    if min_collected:
        sql += " AND collected_at >= ?"
        params.append(min_collected)
    sql += " ORDER BY collected_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_24h():
    """获取过去24小时的新闻（替代 titles_24h.json）"""
    conn = get_db()
    cutoff = time.time() - 86400
    rows = conn.execute(
        "SELECT id, source, title_original, title_cn, link, pub_date, description, "
        "images, full_text, city, lat, lng, has_rss_images, collected_at "
        "FROM news_raw WHERE collected_at >= ? ORDER BY collected_at DESC",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_processed(news_id):
    conn = get_db()
    conn.execute("UPDATE news_raw SET is_processed=1 WHERE id=?", (news_id,))
    conn.commit()
    conn.close()

def count_by_source():
    conn = get_db()
    rows = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM news_raw WHERE collected_at >= ? "
        "GROUP BY source ORDER BY cnt DESC", (time.time() - 86400,)
    ).fetchall()
    conn.close()
    return {r["source"]: r["cnt"] for r in rows}

# ── Popup 操作 ──

def insert_popup(p):
    """插入弹窗记录"""
    conn = get_db()
    conn.execute("""
        INSERT INTO popup (id, news_id, source, title_cn, script, audio_path, images, url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (p["id"], p.get("news_id", ""), p["source"], p["title"], p["script"],
          p.get("audio", ""), json.dumps(p.get("images", [])), p.get("url", ""), time.time()))
    conn.commit()
    conn.close()

def get_recent_popups(limit=20):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM popup ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── 去重（基于 news_raw.id）──

def is_seen(nid):
    """用 news_raw 的 id 去重"""
    conn = get_db()
    r = conn.execute("SELECT 1 FROM news_raw WHERE id=?", (nid,)).fetchone()
    conn.close()
    return r is not None

# ── 统计 ──

def get_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM news_raw").fetchone()[0]
    today = conn.execute(
        "SELECT COUNT(*) FROM news_raw WHERE collected_at >= ?", 
        (time.time() - 86400,)
    ).fetchone()[0]
    processed = conn.execute("SELECT COUNT(*) FROM news_raw WHERE is_processed=1").fetchone()[0]
    popups = conn.execute("SELECT COUNT(*) FROM popup").fetchone()[0]
    conn.close()
    return {"total": total, "today": today, "processed": processed, "popups": popups}

# 初始化
init_db()
