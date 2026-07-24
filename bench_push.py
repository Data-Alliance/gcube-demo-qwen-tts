#!/usr/bin/env python3
"""
bench_push.py — 컨테이너 안에서 실행. Qwen3-TTS 지표를 측정해 pushgateway로 전송.
클러스터 내부(pod)에서 도므로 내부 pushgateway(svc.cluster.local)에 닿는다 → Grafana 표시.

entrypoint가 배포 시 백그라운드로 1회 실행.
- PUSHGATEWAY_URL 있음  → 측정 + pushgateway 전송 (+ 로그 요약)
- BENCH_LOG_ONLY=1     → 측정 + 로그에만 결과 출력(전송 X)
- 둘 다 없음           → 아무것도 안 함(일반 배포엔 영향 X)

env:
  PUSHGATEWAY_URL   전송 대상. 없으면 전송 스킵
  BENCH_LOG_ONLY    1/true → pushgateway 없이 측정해서 로그로만 결과 출력
  RUN_ID            라벨(회차 id), 기본 qwen-bench
  RATE              GPU 시간당 요금(₩/hr) → ₩/1M자 환산 (없으면 GPU명으로 자동 조회)
  GPU_LABEL         GPU 이름 강제 (없으면 NVML 자동)
  BENCH_LANG        기본 ko
  BENCH_SPEAKER     기본 Sohee
  BENCH_COUNT       측정 문장 수, 기본 5
"""
import os
import time
import urllib.request
import urllib.parse

from rates import rate_for

SERVER = os.environ.get("BENCH_SERVER", "http://localhost:8000")

TEXTS = [
    "안녕하세요, 지큐브 음성 합성 데모입니다. 무엇을 도와드릴까요?",
    "잠시 후 안내 말씀 드리겠습니다. 고객 여러분께서는 잠시만 기다려 주시기 바랍니다.",
    "오늘 오후, 인공지능 음성 합성 기술이 새로운 전환점을 맞았습니다.",
    "지금 바로 만나보세요. 당신의 이야기를, 더 자연스러운 목소리로.",
    "이 문장은 음성 합성 성능을 측정하기 위한 예시 문장입니다.",
]

# 요금표·GPU 매핑은 rates.py로 이동(단일 소스). RATES/core_key/rate_for 참조.


def gpu_name():
    lab = os.environ.get("GPU_LABEL", "").strip()
    if lab:
        return lab
    try:
        import pynvml
        pynvml.nvmlInit()
        n = pynvml.nvmlDeviceGetName(pynvml.nvmlDeviceGetHandleByIndex(0))
        n = n.decode() if isinstance(n, bytes) else str(n)
        return n.replace("NVIDIA ", "").replace("GeForce ", "").replace(" ", "")
    except Exception:
        return "unknown"


def one(text, lang, speaker, timeout=300):
    body = urllib.parse.urlencode({
        "text": text, "language": lang, "speaker": speaker, "instruct": "", "speed": "1.0",
    }).encode()
    req = urllib.request.Request(
        SERVER + "/api/tts", data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()  # WAV 본문 소모
        h = r.headers
        return {
            "rtf": float(h.get("X-RTF", 0) or 0),
            "gen": float(h.get("X-Gen-Seconds", 0) or 0),
            "audio": float(h.get("X-Audio-Seconds", 0) or 0),
            "chars": int(h.get("X-Chars", 0) or 0),
            "vram": float(h.get("X-Vram-GB", 0) or 0),
        }


def push(pg, gpu, run, metrics):
    path = f"/metrics/job/qwen_bench/gpu/{gpu}/model/qwen-tts/run/{run}"
    body = "".join(f"{k} {v}\n" for k, v in metrics.items()).encode()
    req = urllib.request.Request(pg.rstrip("/") + path, data=body, method="POST",
                                 headers={"Content-Type": "text/plain"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


def main():
    pg = os.environ.get("PUSHGATEWAY_URL", "").strip()
    log_only = os.environ.get("BENCH_LOG_ONLY", "").strip().lower() in ("1", "true", "yes", "on")
    if not pg and not log_only:
        # 일반 배포: 전송/로그 트리거 둘 다 없으면 벤치 안 함
        print("[bench] PUSHGATEWAY_URL / BENCH_LOG_ONLY 없음 — 벤치 스킵", flush=True)
        return
    run = os.environ.get("RUN_ID", "qwen-bench").strip() or "qwen-bench"
    lang = os.environ.get("BENCH_LANG", "ko")
    speaker = os.environ.get("BENCH_SPEAKER", "Sohee")
    cnt = int(os.environ.get("BENCH_COUNT", "5"))
    gpu = gpu_name()
    rate = float(os.environ.get("RATE", "0") or 0) or (rate_for(gpu) or 0)

    # 서버 준비 + 모델 로드 대기 (워밍업, 콜드 제외)
    print("[bench] 워밍업…", flush=True)
    ok = False
    for _ in range(40):
        try:
            one("안녕하세요.", lang, speaker)
            ok = True
            break
        except Exception:
            time.sleep(5)
    if not ok:
        print("[bench] 서버 준비 안 됨 — 중단", flush=True)
        return

    rtfs, cps, rtfx, vrams = [], [], [], []
    for i in range(cnt):
        try:
            m = one(TEXTS[i % len(TEXTS)], lang, speaker)
            if m["gen"] > 0:
                rtfs.append(m["rtf"])
                cps.append(m["chars"] / m["gen"])
                rtfx.append(m["audio"] / m["gen"])
                vrams.append(m["vram"])
                print(f"[bench] {i+1}/{cnt} rtf={m['rtf']:.3f} chars/s={m['chars']/m['gen']:.1f}", flush=True)
        except Exception as e:
            print(f"[bench] {i+1} 실패: {e}", flush=True)
    if not rtfs:
        print("[bench] 측정값 없음", flush=True)
        return

    mean = lambda a: sum(a) / len(a)
    metrics = {
        "qwen_tts_rtf": round(mean(rtfs), 4),               # 생성시간/오디오길이 (낮을수록 빠름)
        "qwen_tts_rtfx": round(mean(rtfx), 2),              # 실시간 대비 배속 (높을수록 빠름)
        "qwen_tts_chars_per_sec": round(mean(cps), 2),      # 초당 생성 문자수
        "qwen_tts_vram_gb": round(max(vrams), 2),           # VRAM peak
    }
    if rate:
        # ₩/1M자 = rate(₩/hr) × 1,000,000 ÷ (chars/s × 3600)
        metrics["qwen_tts_won_per_1m"] = round(rate * 1_000_000 / (mean(cps) * 3600))

    # 최종 평균 요약 — 전송 여부와 무관하게 항상 로그로 출력
    won = f"  ₩/1M자={metrics['qwen_tts_won_per_1m']}" if "qwen_tts_won_per_1m" in metrics else ""
    print(f"[bench] ===== 결과 평균 (gpu={gpu} run={run} n={len(rtfs)}) =====", flush=True)
    print(f"[bench]   RTF={metrics['qwen_tts_rtf']}  배속={metrics['qwen_tts_rtfx']}  "
          f"자/s={metrics['qwen_tts_chars_per_sec']}  VRAM={metrics['qwen_tts_vram_gb']}GB{won}", flush=True)

    if not pg:
        print("[bench] 로그 전용 모드(BENCH_LOG_ONLY) — pushgateway 전송 안 함", flush=True)
        return

    try:
        push(pg, gpu, run, metrics)
        print(f"[bench] pushed → {pg}  gpu={gpu} run={run}", flush=True)
    except Exception as e:
        print(f"[bench] push 실패: {e}", flush=True)


if __name__ == "__main__":
    main()
