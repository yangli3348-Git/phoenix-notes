#!/usr/bin/env python3
"""新闻聚合·DeepSeek处理·池子推送  v2"""
import json, re, time, random, urllib.request, os, subprocess
from datetime import datetime

# ── 配置 ──
DEEPSEEK_KEY = "sk-9f7eb5c437c74b5ea22af41f230ce2b4"
OUTPUT_FILE = "/tmp/echarts-examples/live_news.json"
CYCLE_INTERVAL = 300       # 主循环5秒（实际按源各自间隔）
DEEPSEEK_INTERVAL = 600    # 至少10分钟才调一次DeepSeek
BATCH_MIN = 5              # 攒够5条才调DeepSeek
POOL_MAX = 80              # 池子最多80条
HISTORY_PER_SOURCE = 50    # 每个源保留50条历史

# ── 新闻源配置 ──
SOURCES = []

# 直连
SOURCES.append({
    'name': 'baidu', 'interval': 180, 'last_fetch': 0,
    'func': 'fetch_baidu', 'history': set()
})
SOURCES.append({
    'name': 'sina', 'interval': 180, 'last_fetch': 0,
    'func': 'fetch_sina', 'history': set()
})
SOURCES.append({
    'name': 'ifeng', 'interval': 600, 'last_fetch': 0,
    'func': 'fetch_ifeng', 'history': set()
})

# 走代理
SOURCES.append({
    'name': 'bbc', 'interval': 600, 'last_fetch': 0,
    'func': 'fetch_bbc', 'history': set()
})
SOURCES.append({
    'name': 'nyt', 'interval': 600, 'last_fetch': 0,
    'func': 'fetch_nyt', 'history': set()
})

# ── 抓取函数 ──
def fetch_baidu():
    req = urllib.request.Request('https://top.baidu.com/board?tab=realtime',
        headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=8) as r:
        html = r.read().decode('utf-8')
    titles = re.findall(r'"word":"([^"]+)"', html)
    return titles[:15]

def fetch_sina():
    req = urllib.request.Request('https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=20',
        headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read().decode('utf-8'))
    return [item.get('title','') for item in data.get('result',{}).get('data',[]) if item.get('title','')][:15]

def fetch_ifeng():
    req = urllib.request.Request('https://news.ifeng.com/',
        headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=8) as r:
        html = r.read().decode('utf-8')
    m = re.search(r'var allData\s*=\s*({.*?});', html, re.DOTALL)
    if m:
        data = json.loads(m.group(1))
        return [item.get('title','') for item in data.get('newsstream',[]) if item.get('title','')][:15]
    return []

def fetch_bbc():
    r = subprocess.run(['curl', '-x', 'http://127.0.0.1:7890', '-s', '--max-time', '10',
        'https://feeds.bbci.co.uk/news/world/rss.xml'],
        capture_output=True, text=True, timeout=12)
    titles = re.findall(r'<title>(?:<!\[CDATA\[)?(.+?)(?:\]\]>)?</title>', r.stdout)
    return titles[1:11] if len(titles) > 1 else []

def fetch_nyt():
    r = subprocess.run(['curl', '-x', 'http://127.0.0.1:7890', '-s', '--max-time', '10',
        'https://rss.nytimes.com/services/xml/rss/nyt/World.xml'],
        capture_output=True, text=True, timeout=12)
    titles = re.findall(r'<title>(?:<!\[CDATA\[)?(.+?)(?:\]\]>)?</title>', r.stdout)
    return titles[1:11] if len(titles) > 1 else []

# ── 调用 DeepSeek ──
def call_deepseek(titles_list):
    """titles_list: [(title, source_name), ...]"""
    lines = "\n".join(f'{i+1}. [{s}] {t}' for i,(t,s) in enumerate(titles_list))
    prompt = f"""你是一个国际新闻处理助手。分析下列新闻标题（中英文混合），返回JSON数组。

每条返回：
  - title: 中文标题（英文需翻译）
  - city: 主要城市（中文名），若无则null
  - lat, lng: 经纬度（无则0）
  - importance: S/A/B/C
  - laps: S=3 A=2 B=1 C=0
  - dedup_key: 去重key（5~15字）

城市坐标：北京[116.46,39.92] 纽约[-74.01,40.71] 伦敦[-0.13,51.51]
东京[139.69,35.69] 莫斯科[37.62,55.76] 华盛顿[-77.04,38.91]
巴黎[2.35,48.86] 柏林[13.40,52.52] 首尔[126.98,37.57]
悉尼[151.21,-33.87] 新加坡[103.82,1.35] 曼谷[100.50,13.76]
迪拜[55.27,25.20] 伊斯坦布尔[28.98,41.01] 开罗[31.24,30.04]
圣保罗[-46.63,-23.55] 德黑兰[35.69,51.42] 耶路撒冷[31.77,35.23]
基辅[30.52,50.45] 德里[28.61,77.20] 台北[25.03,121.57]
香港[22.32,114.17] 加沙[31.50,34.47] 金沙萨[-4.33,15.31]
阿布扎比[54.37,24.47] 日内瓦[6.14,46.20]
其他城市按常识补坐标。

C级不展示(city/lat/lng/laps/dedup_key=null)。只返回S/A/B级，最多{MAX_RETURN}条。
英文标题翻译成通俗中文。

{lines}

只返回JSON数组。"""

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1, "max_tokens": 3000
    }).encode()

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_KEY}"},
        method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=60)
    result = json.loads(resp.read().decode())
    content = result['choices'][0]['message']['content']
    m = re.search(r'\[.*\]', content, re.DOTALL)
    if m:
        return json.loads(m.group())
    return []

# ── 状态 ──
pool = []                # 已处理、待推送
pending = []             # 待处理（未调DeepSeek）
last_ds_time = 0
MAX_RETURN = 15
pushed_titles = {}       # {source_name: {title1, title2, ...

for s in SOURCES:
    pushed_titles[s['name']] = set()

log = print

def push_to_frontend():
    """推送当前池子到前端JSON"""
    # 按重要性排序 + 随机打乱同级
    order = {'S':0, 'A':1, 'B':2}
    pool.sort(key=lambda x: (order.get(x.get('importance','B'), 3), random.random()))
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(pool, f, ensure_ascii=False)
    log(f"  → 推送 {len(pool)} 条到前端")

# ── 主循环 ──
def main():
    global last_ds_time, pool, pending
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    log(f"[启动] 输出: {OUTPUT_FILE}")
    log(f"[启动] {len(SOURCES)} 个新闻源, 池子上限 {POOL_MAX}, DeepSeek批处理阈值 {BATCH_MIN}")

    cycle = 0
    while True:
        cycle += 1
        now = time.time()
        new_titles_for_ds = []  # (title, source_name)

        # 1. 抓取各源
        for src in SOURCES:
            if now - src['last_fetch'] < src['interval']:
                continue
            src['last_fetch'] = now
            try:
                func = globals()[src['func']]
                titles = func()
                history = pushed_titles[src['name']]
                for t in titles:
                    if t not in history:
                        new_titles_for_ds.append((t, src['name']))
                        history.add(t)
                        # 限制历史大小
                        if len(history) > HISTORY_PER_SOURCE * 2:
                            # 丢掉最早的一半
                            history.clear()
                log(f"[抓取] {src['name']}: {len(titles)}条, 其中 {len(new_titles_for_ds) - sum(1 for _ in new_titles_for_ds if _[1]!=src['name'])} 条新")
            except Exception as e:
                log(f"[抓取] {src['name']}: 失败 {e}")

        # 2. 新标题加入待处理
        # 先对比待处理中的去重
        existing_keys = set(t for t,_ in pending)
        for t,s in new_titles_for_ds:
            if t not in existing_keys:
                pending.append((t,s))
                existing_keys.add(t)

        log(f"[状态] 待处理 {len(pending)} 条, 池子 {len(pool)} 条")

        # 3. 判断是否调 DeepSeek
        should_ds = False
        if len(pending) >= BATCH_MIN and now - last_ds_time >= 120:
            should_ds = True
        if now - last_ds_time >= DEEPSEEK_INTERVAL and len(pending) > 0:
            should_ds = True

        if should_ds and len(pending) > 0:
            batch = pending[:20]  # 最多20条一次
            pending = pending[20:]
            last_ds_time = now
            log(f"[DS] 处理 {len(batch)} 条...")
            try:
                results = call_deepseek(batch)
                if results:
                    # 只取S/A/B级
                    keep = [r for r in results if r.get('importance') in ('S','A','B') and (r.get('laps',0) > 0 or r.get('importance') in ('S','A'))]
                    log(f"[DS] 返回 {len(results)}条, 保留 {len(keep)}条 S/A/B")
                    for item in keep:
                        # 简单去重：同一city+dedup_key不再重复加入池子
                        dup = False
                        for p in pool:
                            if p.get('dedup_key') and item.get('dedup_key') and \
                               p['dedup_key'] == item['dedup_key']:
                                dup = True
                                break
                        if not dup:
                            pool.append(item)
                    # 限制池子大小
                    if len(pool) > POOL_MAX:
                        pool = pool[-POOL_MAX:]
                    push_to_frontend()
                else:
                    log(f"[DS] 返回为空")
            except Exception as e:
                log(f"[DS] 失败: {e}")
                # 失败的回退到待处理
                pending = batch + pending
            # 如果待处理还很多，继续处理
            if len(pending) > 0:
                log(f"[DS] 还有 {len(pending)} 条待处理，下一轮循环继续")


        # 4. 如果池子空了就从pending捞几条低配处理（兜底）
        if len(pool) < 5 and len(pending) > 0:
            log(f"[兜底] 池子不足，尝试处理 {len(pending)} 条待处理...")
            batch = pending[:10]
            pending = pending[10:]
            last_ds_time = now
            try:
                results = call_deepseek(batch)
                if results:
                    keep = [r for r in results if r.get('importance') in ('S','A','B') and (r.get('laps',0) > 0 or r.get('importance') in ('S','A'))]
                    for item in keep:
                        dup = False
                        for p in pool:
                            if p.get('dedup_key') and item.get('dedup_key') and \
                               p['dedup_key'] == item['dedup_key']:
                                dup = True; break
                        if not dup:
                            pool.append(item)
                    if len(pool) > POOL_MAX:
                        pool = pool[-POOL_MAX:]
                    push_to_frontend()
            except:
                pending = batch + pending

        time.sleep(CYCLE_INTERVAL)

if __name__ == '__main__':
    main()
