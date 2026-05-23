"""
新闻采集器 — 不同源的采集接口
每个源一个类，统一返回 {title, text, images, url}
"""

import subprocess, re, json
import html as hlib

PROXY = "http://127.0.0.1:7890"

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko"

def http_get(url, use_proxy=False):
    cmd = ["curl", "-sL", "--max-time", "12", "-H", f"User-Agent: {UA}"]
    if use_proxy:
        cmd = ["curl", "-x", PROXY, "-sL", "--max-time", "12", "-H", f"User-Agent: {UA}"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout


class XinhuaFetcher:
    """新华社 — 详情页抓正文，采集JSON字段拿图"""
    name = "xin"

    def fetch(self, item):
        url = item.get("link", "")
        title = item.get("title", "")
        text = ""
        images = []

        # 图片：从采集的 titleImages 字段获取（1.7%的新闻有图）
        ti_list = item.get("titleImages", [])
        for ti in (ti_list if isinstance(ti_list, list) else []):
            if isinstance(ti, dict):
                img_url = ti.get("imageUrl", "")
                if img_url.startswith(".."):
                    img_url = "https://english.news.cn" + img_url[2:]
                if img_url:
                    images.append(img_url)

        # 正文：爬详情页
        html = http_get(url)
        m = re.search(r'<div id="detailContent">(.+?)</div>', html, re.DOTALL)
        if m:
            parts = []
            for p in re.findall(r'<p>(.+?)</p>', m.group(1), re.DOTALL):
                t = re.sub(r'<[^>]+>', '', p).strip()
                t = re.sub(r'\s+', ' ', t)
                if len(t) > 20:
                    parts.append(t)
            text = " ".join(parts)

        if len(text) < 50:
            text = title

        return {"title": title, "text": text, "images": images, "url": url}


class BBCFetcher:
    """BBC — JSON-LD + text-block"""
    name = "bbc"

    def fetch(self, item):
        title = item.get("title", "")
        url = item["link"].replace("<![CDATA[","").replace("]]>","").split("?")[0]
        text = ""
        images = []

        html = http_get(url, use_proxy=True)

        # JSON-LD
        ld_m = re.search(r'application/ld\+json[^>]*>\s*(\{.*?\})\s*</script>', html)
        if ld_m:
            try:
                meta = json.loads(ld_m.group(1))
                if meta.get("headline"):
                    title = meta["headline"]
        # JSON-LD image — 可能是 dict 或 list
                img = meta.get("image", {})
                if isinstance(img, dict) and img.get("url"):
                    images.append(img["url"])
                elif isinstance(img, list):
                    for i in img:
                        if isinstance(i, str) and not i.endswith('.png') and 'favicon' not in i:
                            images.append(i)
                        elif isinstance(i, dict) and i.get("url"):
                            images.append(i["url"])
            except:
                pass

        # og:image fallback
        if not images:
            og = re.search(r'property="og:image"[^>]*content="([^"]+)"', html)
            if og:
                images.append(og.group(1))

        # text-block
        tbs = re.findall(r'<div[^>]*data-component="text-block"[^>]*>(.*?)</div>', html)
        parts = []
        for block in tbs[:20]:
            t = hlib.unescape(re.sub(r'<[^>]+>', ' ', block)).strip()
            t = re.sub(r'\s+', ' ', t)
            if len(t) > 20:
                parts.append(t)
        text = " ".join(parts) if parts else title

        return {"title": title, "text": text, "images": images, "url": url}


class RTFetcher:
    """RT — article__text + og:image"""
    name = "rt"

    def fetch(self, item):
        title = item.get("title", "")
        url = item["link"].replace("<![CDATA[","").replace("]]>","").split("?")[0]
        text = ""
        images = []

        html = http_get(url, use_proxy=True)

        img_m = re.search(r'property="og:image"[^>]*content="([^"]+)"', html)
        if img_m:
            images.append(img_m.group(1))

        ab = re.search(r'class="article__text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if ab:
            t = hlib.unescape(re.sub(r'<[^>]+>', ' ', ab.group(1))).strip()
            text = re.sub(r'\s+', ' ', t)

        if len(text) < 50:
            text = title

        return {"title": title, "text": text, "images": images, "url": url}


class DWFetcher:
    """DW — JSON-LD image list + og:image + p标签"""
    name = "dw"

    def fetch(self, item):
        title = item.get("title", "")
        url = item["link"].replace("<![CDATA[","").replace("]]>","").split("?")[0]
        text = ""
        images = []

        html = http_get(url, use_proxy=True)

        # JSON-LD image (list)
        ld_m = re.search(r'application/ld\+json[^>]*>\s*(\{.*?\})\s*</script>', html)
        if ld_m:
            try:
                meta = json.loads(ld_m.group(1))
                img = meta.get("image", [])
                if isinstance(img, list):
                    for i in img:
                        if isinstance(i, str) and not i.endswith('.png') and 'favicon' not in i:
                            images.append(i)
                elif isinstance(img, dict) and img.get("url"):
                    images.append(img["url"])
            except: pass

        # og:image fallback
        if not images:
            og = re.search(r'property="og:image"[^>]*content="([^"]+)"', html)
            if og:
                images.append(og.group(1))

        # 正文
        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        parts = []
        for p in paras[:30]:
            t = hlib.unescape(re.sub(r'<[^>]+>', ' ', p)).strip()
            t = re.sub(r'\s+', ' ', t)
            if len(t) > 25:
                parts.append(t)
        text = " ".join(parts[:15]) if parts else title

        return {"title": title, "text": text, "images": images, "url": url}


class GenericRSSFetcher:
    """CNN / AJ / F24 通用 — og:image + p标签"""
    name = "generic"

    def __init__(self, name):
        self.name = name

    def fetch(self, item):
        title = item.get("title", "")
        url = item["link"].replace("<![CDATA[","").replace("]]>","").split("?")[0]
        text = ""
        images = []

        html = http_get(url, use_proxy=True)

        img_m = re.search(r'property="og:image"[^>]*content="([^"]+)"', html)
        if img_m:
            images.append(img_m.group(1))

        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        parts = []
        for p in paras[:30]:
            t = hlib.unescape(re.sub(r'<[^>]+>', ' ', p)).strip()
            t = re.sub(r'\s+', ' ', t)
            if len(t) > 25:
                parts.append(t)
        text = " ".join(parts[:15]) if parts else title

        return {"title": title, "text": text, "images": images, "url": url}




class TASSFetcher:
    """塔斯社 — 正文在 text-block p标签, og:image在meta"""
    name = "tass"

    def fetch(self, item):
        title = item.get("title", "")
        url = item.get("link", "")
        if "<![CDATA[" in url:
            url = url.replace("<![CDATA[","").replace("]]>","")
        url = url.split("?")[0]
        text = ""
        images = []

        html = http_get(url, use_proxy=True)

        # og:image
        og = re.search(r'property="og:image"[^>]*content="([^"]+)"', html)
        if og:
            images.append(og.group(1))

        # JSON-LD image fallback
        ld_m = re.search(r'application/ld\+json[^>]*>\s*(\{.*?\})\s*</script>', html)
        if ld_m:
            try:
                meta = json.loads(ld_m.group(1))
                ld_img = meta.get("image", [])
                if isinstance(ld_img, str) and not images:
                    images.append(ld_img)
                elif isinstance(ld_img, list) and not images:
                    for i in ld_img:
                        if isinstance(i, str):
                            images.append(i)
            except: pass

        # 正文: div.text-content 里的所有 p 标签
        tc = re.search(r'<div class="text-content">(.*?)<div class="column">', html, re.DOTALL)
        if tc:
            parts = []
            for p in re.findall(r'<p>(.*?)</p>', tc.group(1), re.DOTALL):
                t = hlib.unescape(re.sub(r'<[^>]+>', ' ', p)).strip()
                t = re.sub(r'\s+', ' ', t)
                if len(t) > 20:
                    parts.append(t)
            text = " ".join(parts)

        if len(text) < 50:
            text = title

        return {"title": title, "text": text, "images": images, "url": url}


class NYTFetcher:
    """NYT — 优先用 RSS description + images (绕过 paywall)，失败则抓详情"""
    name = "nyt"

    def fetch(self, item):
        title = item.get("title", "")
        url = item.get("link", "")
        # RSS 预取数据
        description = item.get("description", "")
        images = item.get("images", [])

        # 如果 RSS 已有足够文字直接返回
        if description and len(description) >= 100:
            return {"title": title, "text": description, "images": images, "url": url}

        # fallback: 抓详情页（但 NYT 大多有 paywall，内容可能很少）
        html = http_get(url, use_proxy=True)
        text = title
        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        parts = []
        for p in paras[:20]:
            t = hlib.unescape(re.sub(r'<[^>]+>', ' ', p)).strip()
            t = re.sub(r'\s+', ' ', t)
            if len(t) > 25:
                parts.append(t)
        if parts:
            text = " ".join(parts)

        if not images:
            og = re.search(r'property="og:image"[^>]*content="([^"]+)"', html)
            if og:
                images.append(og.group(1))

        return {"title": title, "text": text if len(text) > 50 else description or title,
                "images": images, "url": url}


# ── 工厂 ──
FETCHERS = {
    "xin-world": XinhuaFetcher(),
    "bbc":       BBCFetcher(),
    "rt":        RTFetcher(),
    "dw":        DWFetcher(),
    "cnn":       GenericRSSFetcher("cnn"),
    "aj":        GenericRSSFetcher("aj"),
    "f24":       GenericRSSFetcher("f24"),
    "nyt":       NYTFetcher(),
    "tass":      TASSFetcher(),
}

def fetch(source, item):
    fetcher = FETCHERS.get(source)
    if not fetcher:
        return None
    return fetcher.fetch(item)
