"""
口播生成器 — DeepSeek 编译中文标题+口播稿
"""

import requests

DEEPSEEK_KEY = "sk-9f7eb5c437c74b5ea22af41f230ce2b4"
API_URL = "https://api.deepseek.com/v1/chat/completions"

PROMPT = """你是新闻口播编辑，将以下英文新闻编译为中文。

请输出两行，格式如下：
标题：xxx（10-15字中文标题）
口播：xxx（110-130字中文口播，自然口语化）

来源：{source}
英文标题：{title}

新闻内容：
{text}"""

def generate(detail):
    title = detail["title"]
    text = detail["text"][:2000]
    source = detail.get("source", "").upper()

    prompt = PROMPT.format(source=source, title=title, text=text)

    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 300, "temperature": 0.7},
            timeout=30
        )
        content = resp.json()["choices"][0]["message"]["content"].strip()

        cn_title = title   # fallback
        script = ""
        for line in content.split("\n"):
            line = line.strip().replace("**","")
            if line.startswith("标题：") or line.startswith("标题:"):
                cn_title = line.split("：")[-1].split(":")[-1].strip()
            elif line.startswith("口播：") or line.startswith("口播:"):
                script = line.split("：")[-1].split(":")[-1].strip()

        if not script:
            script = content

        return cn_title, script
    except Exception as e:
        print(f"  ❌ DeepSeek: {e}")
        return None, None
