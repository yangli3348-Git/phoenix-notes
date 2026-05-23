"""
源配置中心 — 唯一真相源
collector 和 fetcher 共用这里的 URL / 代理 / 类型 配置
"""

PROXY_URL = "http://127.0.0.1:7890"

SOURCES = [
    {
        "name": "xin-world",
        "label": "新华社",
        "type": "xin_json",  # collector 采集方式
        "fetcher": "xin",     # fetcher.py 详情抓取方式
        "url": "https://english.news.cn/world/ds_7718692eb4e54a328c7913da6f673e4b.json",
        "proxy": False,
    },
    {
        "name": "bbc",
        "label": "BBC",
        "type": "rss",
        "fetcher": "bbc",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "proxy": True,
    },
    {
        "name": "rt",
        "label": "RT",
        "type": "rss",
        "fetcher": "rt",
        "url": "https://www.rt.com/rss/news/",
        "proxy": True,
    },
    {
        "name": "dw",
        "label": "德国之声",
        "type": "rss",
        "fetcher": "dw",
        "url": "https://rss.dw.com/rdf/rss-en-all",
        "proxy": True,
    },
    {
        "name": "cnn",
        "label": "CNN",
        "type": "rss",
        "fetcher": "generic",
        "url": "http://rss.cnn.com/rss/edition.rss",
        "proxy": True,
    },
    {
        "name": "aj",
        "label": "半岛电视台",
        "type": "rss",
        "fetcher": "generic",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "proxy": True,
    },
    {
        "name": "f24",
        "label": "法国24",
        "type": "rss",
        "fetcher": "generic",
        "url": "https://www.france24.com/en/rss",
        "proxy": False,
    },
    {
        "name": "nyt",
        "label": "纽约时报",
        "type": "rss",
        "fetcher": "nyt",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "proxy": True,
    },
    {
        "name": "tass",
        "label": "塔斯社",
        "type": "rss",
        "fetcher": "tass",
        "url": "https://tass.com/rss/v2.xml",
        "proxy": True,  # 需要代理+User-Agent
    },
]

# 索引
BY_NAME = {s["name"]: s for s in SOURCES}


def get_proxy(name):
    """某源是否需要代理"""
    s = BY_NAME.get(name)
    return s["proxy"] if s else False
