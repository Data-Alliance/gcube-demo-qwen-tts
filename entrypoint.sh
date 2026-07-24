#!/bin/sh
set -e

# 1) GPU 지표 수집 (백그라운드) → gpu.json
python3 gpu_metrics.py &

# 2) 벤치 (백그라운드 1회). 아래 둘 중 하나가 설정됐을 때만 실행 = 명시적 opt-in.
#    - PUSHGATEWAY_URL : 측정 후 pushgateway 전송
#    - BENCH_LOG_ONLY  : 측정 후 로그에만 출력(전송 X)
#    둘 다 없으면 스킵 = 일반 배포엔 영향 없음(서버만 뜸)
if [ -n "$PUSHGATEWAY_URL" ] || [ -n "$BENCH_LOG_ONLY" ]; then
    python3 bench_push.py &
fi

# 3) 서버 (포그라운드 = 컨테이너 메인 프로세스)
#    --workers 1 : 단일 워커 = 단일 스트림 (데모 측정 기준)
exec uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1
