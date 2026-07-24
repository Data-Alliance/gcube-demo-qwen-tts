"""Qwen3-TTS CustomVoice 추론 래퍼 (PyTorch, bfloat16).
프리셋 화자(한국어=Sohee 등) + instruct(톤/감정 지시). 세션 1회 로드, 직렬화는 server에서."""
import os

import numpy as np
import torch
from qwen_tts import Qwen3TTSModel

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
# flash_attention_2는 별도 컴파일(빌드) 필요 → sdpa 기본(추가 의존성 없음)
ATTN_IMPL = os.environ.get("ATTN_IMPL", "sdpa")

# 추론 가속 (안전·무료): TF32 matmul 허용
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
# cudnn.benchmark: 입력 길이가 매번 다른 TTS에선 길이마다 재튜닝해 오히려 손해
# (첫 요청마다 느려지고 측정 편차↑) → 끔.
torch.backends.cudnn.benchmark = False


class QwenTTS:
    def __init__(self):
        dev = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.model = Qwen3TTSModel.from_pretrained(
            MODEL_ID,
            device_map=dev,
            dtype=torch.bfloat16,
            attn_implementation=ATTN_IMPL,
        )
        self.last_peak_gb = 0.0  # 직전 generate의 VRAM peak (server가 헤더로 노출)
        print(f"[qwen_tts] loaded {MODEL_ID} on {dev} (attn={ATTN_IMPL})", flush=True)

    def generate(self, text, language="Korean", speaker="Sohee", instruct=None):
        """텍스트 → 오디오(np.float32 1D), sample_rate 반환."""
        kwargs = dict(text=text, language=language, speaker=speaker)
        if instruct:
            kwargs["instruct"] = instruct
        cuda = torch.cuda.is_available()
        if cuda:
            torch.cuda.reset_peak_memory_stats()  # 이번 생성의 진짜 peak 측정 시작점
        wavs, sr = self.model.generate_custom_voice(**kwargs)
        wav = np.asarray(wavs[0], dtype=np.float32).squeeze()
        if cuda:
            # empty_cache() 전에 읽어야 생성 중 실제 최댓값이 잡힘 (캐시 비운 뒤 값 X)
            self.last_peak_gb = torch.cuda.max_memory_allocated() / 1e9
            torch.cuda.empty_cache()  # 반복 생성 시 VRAM 파편화 방지 (8GB 여유 확보)
        return wav, int(sr)
