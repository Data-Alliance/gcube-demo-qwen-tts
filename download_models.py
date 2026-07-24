"""빌드 단계 전용 — 모델을 이미지에 굽는다(캐시).
이 파일만 안 바뀌면 재빌드 시 재다운로드 없음(코드만 고쳐도 빠름).
HF 일시 오류(504 등)에 안 죽게 재시도 + resume."""
import os
import time

os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")  # 느린 응답 관대하게

from huggingface_hub import snapshot_download

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")

last = None
for attempt in range(1, 7):
    try:
        # resume 기본 지원 → 재시도 시 받던 것 이어받음
        snapshot_download(repo_id=MODEL_ID, max_workers=4)
        print(f"[download_models] {MODEL_ID} done (try {attempt})", flush=True)
        break
    except Exception as e:
        last = e
        print(f"[download_models] try {attempt} 실패: {e}", flush=True)
        time.sleep(15)
else:
    raise SystemExit(f"[download_models] 다운로드 6회 실패: {last}")
