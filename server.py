"""
qwen-tts 서버 — gcube 데모(z-image·VibeThinker와 같은 패턴)의 TTS 버전.
Qwen3-TTS CustomVoice → 프리셋 화자(한국어=Sohee 등) 음성 합성 + instruct(톤/감정 지시).
속도는 생성 후 time-stretch(피치 유지)로 후처리. 단일 스트림(lock)으로 직렬화.
FastAPI 하나로 웹UI + /api/tts + /gpu.json 서빙.
"""
import io
import time
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import librosa
import soundfile as sf
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import Response, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from qwen_tts_engine import QwenTTS

BASE = Path(__file__).parent
GPU_JSON = BASE / "gpu.json"  # gpu_metrics.py가 1초마다 기록 → 웹UI가 폴링

# UI 언어코드 → Qwen 언어명
LANG_MAP = {"ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese"}

_model = None
_lock = threading.Lock()  # 단일 스트림 — 요청 직렬화

try:
    import pynvml
    pynvml.nvmlInit()
    _nvml = pynvml.nvmlDeviceGetHandleByIndex(0)
except Exception:
    pynvml, _nvml = None, None


def _vram_used_gb():
    if _nvml is None:
        return 0.0
    try:
        return pynvml.nvmlDeviceGetMemoryInfo(_nvml).used / 1e9
    except Exception:
        return 0.0


def get_model():
    global _model
    if _model is None:
        _model = QwenTTS()
    return _model


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 기동 시 모델 로드 + 커널 워밍업(더미 1건) → 첫 실요청부터 빠름
    try:
        m = get_model()
        m.generate("안녕하세요.", language="Korean", speaker="Sohee")  # 워밍업
        print("[startup] model loaded + warmed up", flush=True)
    except Exception as e:
        print(f"[startup] model load/warmup 실패: {e}", flush=True)
    yield


app = FastAPI(title="gcube Qwen3-TTS", lifespan=lifespan)


@app.post("/api/tts")
def tts(
    text: str = Form(...),
    language: str = Form("ko"),
    speaker: str = Form("Sohee"),
    instruct: str = Form(""),
    speed: float = Form(1.0),
):
    if not text or not text.strip():
        raise HTTPException(400, "text가 비어 있습니다.")
    lang = LANG_MAP.get(language, "Korean")

    model = get_model()
    with _lock:
        t0 = time.time()
        wav, sr = model.generate(text, language=lang, speaker=speaker,
                                 instruct=(instruct.strip() or None))
        gen_s = time.time() - t0
        if abs(speed - 1.0) > 1e-3:  # 배속(피치 유지)
            wav = librosa.effects.time_stretch(wav, rate=float(speed))
        # 생성 중 실제 peak(엔진이 empty_cache 전에 기록). CPU 등으로 0이면 NVML 폴백.
        vram_gb = model.last_peak_gb or _vram_used_gb()

    audio_s = len(wav) / sr
    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="WAV")
    buf.seek(0)
    rtf = (gen_s / audio_s) if audio_s else 0.0
    headers = {
        "X-Gen-Seconds": f"{gen_s:.2f}",
        "X-Audio-Seconds": f"{audio_s:.2f}",
        "X-RTF": f"{rtf:.3f}",
        "X-Vram-GB": f"{vram_gb:.2f}",
        "X-Chars": str(len(text)),
        "X-Speaker": speaker,
        "X-Speed": f"{speed:.2f}",
        "Access-Control-Expose-Headers":
            "X-Gen-Seconds,X-Audio-Seconds,X-RTF,X-Vram-GB,X-Chars,X-Speaker,X-Speed",
    }
    print(
        f"[tts] chars={len(text)} lang={lang} speaker={speaker} spd={speed} "
        f"instruct={'Y' if instruct.strip() else 'N'} gen={gen_s:.2f}s "
        f"audio={audio_s:.2f}s rtf={rtf:.3f} vram={vram_gb:.2f}GB",
        flush=True,
    )
    return Response(content=buf.read(), media_type="audio/wav", headers=headers)


@app.get("/gpu.json")
def gpu():
    if GPU_JSON.exists():
        try:
            return JSONResponse(json.loads(GPU_JSON.read_text(encoding="utf-8")))
        except Exception:
            pass
    return JSONResponse({})


@app.get("/")
def index():
    return FileResponse(BASE / "index.html")


app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
