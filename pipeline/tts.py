"""
语音合成 — Edge TTS 微软晓晓
"""

import subprocess, os

VOICE = "zh-CN-XiaoxiaoNeural"
RATE = "+8%"

def synthesize(text, output_path):
    """返回 True/False"""
    try:
        subprocess.run(
            ["edge-tts", "--voice", VOICE, "--text", text,
             f"--rate={RATE}", "--write-media", output_path],
            capture_output=True, timeout=30
        )
        return os.path.exists(output_path)
    except:
        return False
