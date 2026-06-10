"""Kiểm tra nhanh API key: gọi 1 request dịch nhỏ bằng model trong config."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic

import config

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
r = client.messages.create(
    model=config.CLAUDE_MODEL,
    max_tokens=64,
    messages=[{"role": "user", "content": "Dịch sang tiếng Việt, chỉ trả về bản dịch: 被嘲笑为E级废物，我觉醒了SSS级天赋"}],
)
print("Model:", r.model)
print("Dịch thử:", r.content[0].text.strip())
print(f"Token: {r.usage.input_tokens} vào / {r.usage.output_tokens} ra")
cost = r.usage.input_tokens * 1e-6 * 1.0 + r.usage.output_tokens * 1e-6 * 5.0
print(f"Chi phí request này: ${cost:.6f}")
