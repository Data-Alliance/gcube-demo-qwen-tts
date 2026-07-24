description: "Qwen3-TTS CustomVoice 음성합성(TTS) 데모 (한국어 화자 Sohee)"
cuda: "" # 비워둠 — torch cu128 휠이 CUDA 런타임 자체 포함 (Blackwell/RTX50 지원, 선택값)
sharedMemory: 1

containers:
  - containerImage: "yjoh/qwen-tts:latest" # Docker Hub 공개
    repo: docker.io # Docker Hub (ECR Public 데이터 한도 회피 — 큰 이미지)
    port: 8000 # uvicorn (Dockerfile EXPOSE 8000 / entrypoint uvicorn :8000)
    maxConnection: 20 # 웹 UI 기준(gpu.json 폴링+다중 뷰어). GPU는 lock으로 1건씩 직렬화라 안전
    containerCommand: ""
    isCredential: false # Docker Hub 공개 repo → 인증 불필요
    containerEnvs: [] # 별도 키 없음 (Qwen3-TTS 한국어 네이티브). 필요시 ATTN_IMPL=eager 등
    userStorages: [] # 마운트 없음 (오디오 저장 X, 모델은 이미지에 구움)
