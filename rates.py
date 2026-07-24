"""GPU 시간당 요금표(원) — 단일 소스(single source of truth).
bench_push.py·gpu_metrics.py가 import해서 쓰고, 웹UI는 gpu_metrics가 gpu.json에
실어 보내는 rate를 그대로 사용한다(app.js에 요금표 중복 X). 값 수정은 여기 한 곳만.
기준: gcube-demo 비교탭(pricing.js)."""
import re

RATES = {
    "5090": 1159, "4090": 489, "4080": 326,
    "5060ti": 309, "5060": 121, "4060ti": 168, "4060": 168,
    "3080": 92, "3070": 75, "a100": 4270, "h100": 9200,
}


def core_key(name=""):
    """GPU 이름 → 요금표 키 (예: 'NVIDIA GeForce RTX 5060 Ti' → '5060ti')."""
    t = str(name).lower()
    if "h100" in t:
        return "h100"
    if "a100" in t:
        return "a100"
    m = re.search(r"(\d{4})", t)
    return (m.group(1) + ("ti" if "ti" in t else "")) if m else ""


def rate_for(name):
    """GPU 이름 → 시간당 요금(원). 모르면 None."""
    return RATES.get(core_key(name))
