"""NVML로 GPU 사용률·VRAM을 1초마다 gpu.json에 기록. 웹UI가 /gpu.json 폴링해 표시.
(nvidia-smi CLI는 주입 노드에서 exec 불가할 수 있어 pynvml 사용)"""
import json
import time
from pathlib import Path

import pynvml

from rates import rate_for

OUT = Path(__file__).parent / "gpu.json"


def main():
    pynvml.nvmlInit()
    h = pynvml.nvmlDeviceGetHandleByIndex(0)
    name = pynvml.nvmlDeviceGetName(h)
    if isinstance(name, bytes):
        name = name.decode()
    rate = rate_for(name)  # 시간당 요금(원) → gpu.json에 실어 UI가 그대로 사용
    while True:
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(h).gpu
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            OUT.write_text(
                json.dumps(
                    {
                        "name": name,
                        "util": util,
                        "vram_used_gb": round(mem.used / 1e9, 2),
                        "vram_total_gb": round(mem.total / 1e9, 2),
                        "rate": rate,
                    }
                ),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[gpu_metrics] {e}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
