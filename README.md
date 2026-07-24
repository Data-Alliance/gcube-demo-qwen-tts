# gcube Qwen3-TTS Demo

Qwen3-TTS(음성 합성)를 gcube GPU 클라우드에 **서빙 컨테이너 + 웹 데모**로 배포하는 프로젝트. z-image(이미지 생성)·VibeThinker(추론 LLM) 데모와 동일한 패턴으로, 단일 컨테이너 안에 모델·API·웹UI·GPU 지표·벤치마크를 모두 포함한다.

- **모델:** [Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) (Alibaba, Apache-2.0)
- **화자:** 프리셋 화자(한국어 = Sohee 등), instruct(톤/감정 지시) 지원
- **런타임:** PyTorch cu128 / bfloat16 (Blackwell·RTX 50 계열 sm_120 지원)

---

## 주요 기능

- **웹 데모 UI** — 텍스트 입력 → 음성 생성·재생, 실시간 GPU 사용률/VRAM 표시
- **REST API** — `POST /api/tts` (텍스트→WAV), 응답 헤더로 RTF·생성시간·VRAM 등 지표 노출
- **단일 스트림 서빙** — GPU 추론을 lock으로 직렬화(1건씩) → 실사용자 체감 성능 기준
- **자동 벤치마크** — 기동 시 지표 측정 후 Prometheus Pushgateway 전송 → gcube Grafana 비교(옵션)
- **자가완결형 이미지** — 모델을 이미지에 구워 외부 의존 없이 배포

---

## 파일 구성

| 파일 | 역할 |
|---|---|
| `Dockerfile` | 서빙 이미지 빌드 (torch cu128 설치 + 모델 굽기 + 앱 코드) |
| `download_models.py` | 빌드 단계에서 모델을 이미지에 다운로드(캐시, 재시도/resume) |
| `qwen_tts_engine.py` | Qwen3-TTS 추론 래퍼 (bfloat16, VRAM peak 측정) |
| `server.py` | FastAPI — 웹UI + `POST /api/tts` + `GET /gpu.json` |
| `gpu_metrics.py` | NVML로 GPU 사용률·VRAM을 1초마다 `gpu.json`에 기록 |
| `bench_push.py` | 지표 측정(워밍업→N회→평균) 후 Pushgateway 전송 |
| `rates.py` | GPU 시간당 요금표(₩/hr) — 비용(₩/1M자) 산출용 단일 소스 |
| `index.html`, `static/` | 웹 데모 UI |
| `entrypoint.sh` | GPU 지표 수집 + (옵션)벤치 + uvicorn 서버 실행 |
| `workload.yml` | gcube 워크로드 배포 정의 |

---

## 빌드 & 배포

### 1. Docker 이미지 빌드·푸시
```bash
docker build --provenance=false -t yjoh/qwen-tts:latest .
docker push yjoh/qwen-tts:latest
```
> 모델(수 GB)을 이미지에 굽기 때문에 최초 빌드는 시간이 걸린다. `download_models.py`가 안 바뀌면 모델 레이어는 캐시되어 코드만 고칠 땐 재다운로드하지 않는다.

### 2. gcube 배포
`workload.yml`로 워크로드를 배포한다 (이미지 `yjoh/qwen-tts:latest`, 포트 `8000`).
배포 후 노출된 URL로 접속하면 웹 데모가 뜬다.

### 3. 로컬 실행 (GPU 필요)
```bash
docker run --gpus all -p 8000:8000 yjoh/qwen-tts:latest
```
브라우저에서 `http://localhost:8000` 접속.

---

## API

### `POST /api/tts`
`application/x-www-form-urlencoded`

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `text` | (필수) | 합성할 텍스트 |
| `language` | `ko` | `ko` / `en` / `ja` / `zh` |
| `speaker` | `Sohee` | 프리셋 화자 |
| `instruct` | (없음) | 톤/감정 지시(옵션) |
| `speed` | `1.0` | 배속(피치 유지, time-stretch 후처리) |

**응답:** `audio/wav` 본문 + 지표 헤더 — `X-RTF`, `X-Gen-Seconds`, `X-Audio-Seconds`, `X-Vram-GB`, `X-Chars` 등

### `GET /gpu.json`
현재 GPU 이름·사용률·VRAM·시간당 요금 (웹UI가 폴링).

---

## 벤치마크 (옵션)

`entrypoint.sh`가 기동 시 아래 환경변수가 있을 때만 `bench_push.py`를 1회 실행한다 (없으면 서버만 뜸).

| 환경변수 | 설명 |
|---|---|
| `PUSHGATEWAY_URL` | 측정 후 Pushgateway로 전송 (없으면 전송 스킵) |
| `BENCH_LOG_ONLY` | `1`이면 전송 없이 로그에만 결과 출력 |
| `RUN_ID` | 측정 회차 라벨 (기본 `qwen-bench`) |
| `BENCH_COUNT` | 측정 문장 수 (기본 5) |
| `RATE` | GPU 시간당 요금(₩/hr). 없으면 GPU명으로 `rates.py`에서 자동 조회 |
| `GPU_LABEL` | GPU 이름 강제 (없으면 NVML 자동 감지) |
| `BENCH_LANG` / `BENCH_SPEAKER` | 기본 `ko` / `Sohee` |

**측정 지표:** RTF(생성시간/오디오길이), 배속(RTFx), 자/s(chars/sec), VRAM peak, ₩/1M자
gcube Grafana에서 `qwen_tts_*` 지표를 `gpu` 라벨로 비교.

---

## 설계 노트

- **cu128 필수** — Blackwell/RTX 50(sm_120)은 cu124 휠에 커널이 없어 `no kernel image available` 에러. torch를 cu128 인덱스에서 설치.
- **단일 스트림** — `_lock`으로 추론을 직렬화. 실사용자(1요청씩) 체감 성능을 재는 기준이며, 최대 처리량(동시성)과는 다른 측정.
- **워밍업** — 기동 시 더미 1건 생성으로 CUDA 커널 콜드 비용 제거 → 첫 실요청부터 정상 속도.
- **VRAM peak** — `empty_cache()` 전에 `max_memory_allocated()`를 읽어 생성 중 실제 최댓값을 기록.
- **TF32 on / cudnn.benchmark off** — 안전한 matmul 가속은 켜되, 입력 길이가 매번 다른 TTS에선 benchmark 재튜닝이 오히려 손해라 끔.
