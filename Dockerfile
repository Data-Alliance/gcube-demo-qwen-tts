# Qwen3-TTS CustomVoice (TTS) 서빙 — gcube 데모
# qwen-tts = Python 3.12+ 필요. torch cu128 휠(Blackwell/RTX50 지원) — cu124는 최신 GPU 커널 없음.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models

# libsndfile/ffmpeg/sox=오디오 I/O, libgomp1=torch 런타임, git=일부 pip 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg sox git libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch + torchaudio를 같은 cu128 인덱스에서 함께 (Blackwell/RTX50 sm_120 커널 포함)
# cu124는 최신 GPU에서 "no kernel image available" 에러 → cu128 필수. 먼저 설치해 mismatch 방지.
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu128
RUN pip install --no-cache-dir \
    qwen-tts accelerate \
    fastapi "uvicorn[standard]" python-multipart \
    soundfile librosa pynvml

# 모델 굽기 먼저: download_models.py만 안 바뀌면 캐시 → 코드 수정해도 재다운로드 없음
COPY download_models.py ./
RUN python3 download_models.py

# 앱 코드 (자주 바뀜 → 위 모델 캐시 유지)
COPY qwen_tts_engine.py server.py gpu_metrics.py bench_push.py rates.py entrypoint.sh ./
COPY index.html ./
COPY static ./static

RUN chmod +x entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
