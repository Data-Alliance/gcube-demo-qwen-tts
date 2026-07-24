const $ = (id) => document.getElementById(id);
const setV = (id, val, unit) =>
  ($(id).innerHTML = val + (unit ? `<small>${unit}</small>` : ""));

// 시간당 요금은 서버(gpu_metrics.py)가 gpu.json의 rate로 실어 보냄 → UI는 그대로 사용.
// (요금표 단일 소스 = rates.py. app.js에 요금표 중복 없음 → 값 어긋날 일 없음)
let curRate = null; // 현재 GPU 시간당 요금(원)

// 언어별 프리셋 화자 (Qwen3-TTS CustomVoice)
const SPEAKERS = {
  ko: ["Sohee"],
  en: ["Ryan", "Aiden"],
  ja: ["Ono_Anna"],
  zh: ["Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric"],
};

const q = $("q"), btn = $("run"), lang = $("lang");
const speaker = $("speaker"), instruct = $("instruct"), spd = $("spd");
let running = false;
let curUrl = null;
let audioCtx = null;

const S = { count: 0, genS: 0, audioS: 0, chars: 0, rtfSum: 0, costS: 0 };

// ── 화자 목록(언어 따라 갱신) ──
function fillSpeakers() {
  const list = SPEAKERS[lang.value] || [];
  speaker.innerHTML = list.map((s) => `<option value="${s}">${s}</option>`).join("");
}
lang.addEventListener("change", fillSpeakers);
fillSpeakers();

// ── 프리셋 ──
$("presets").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (chip) q.value = chip.dataset.t;
});

// ── 속도 슬라이더 ──
spd.addEventListener("input", () => ($("spdV").textContent = Number(spd.value).toFixed(2) + "x"));

// ── 글자 수 + 예상 비용 (라이브) ──
function updateCharCount() {
  const n = q.value.length;
  let t = n.toLocaleString() + "자";
  if (S.chars > 0 && curRate != null) {
    // 세션 평균 생성속도(초/자)로 예상 비용 추정
    const est = ((n * (S.genS / S.chars)) / 3600) * curRate;
    t += ` · 예상 ~${est.toFixed(2)}원`;
  }
  $("charCount").textContent = t;
}
q.addEventListener("input", updateCharCount);
updateCharCount();

// ── 음성 생성 ──
async function generate() {
  if (running) return;
  const text = q.value.trim();
  if (!text) return;
  running = true;
  btn.disabled = true;
  $("status").textContent = "음성 생성 중… (첫 요청은 모델 준비로 느릴 수 있어요)";
  $("result").classList.remove("show");
  try {
    const fd = new FormData();
    fd.append("text", text);
    fd.append("language", lang.value);
    fd.append("speaker", speaker.value);
    fd.append("instruct", instruct.value);
    fd.append("speed", spd.value);

    const res = await fetch("/api/tts", { method: "POST", body: fd });
    if (!res.ok) {
      $("status").textContent = "[오류 " + res.status + "] " + (await res.text());
      return;
    }
    const blob = await res.blob();
    if (curUrl) URL.revokeObjectURL(curUrl);
    curUrl = URL.createObjectURL(blob);
    $("audio").src = curUrl;
    $("audio").play().catch(() => {});

    const h = (k) => res.headers.get(k);
    const rtf = h("X-RTF"), gen = h("X-Gen-Seconds"), aud = h("X-Audio-Seconds");
    const vram = h("X-Vram-GB"), chars = h("X-Chars");
    setV("mRtf", rtf ?? "—");
    setV("mGen", gen ?? "—", "s");
    setV("mAudio", aud ?? "—", "s");
    setV("mChars", chars ?? "—");
    setV("mVram", vram ?? "—", "GB");
    $("result").classList.add("show");
    $("status").textContent = "";

    // 파형 시각화 (blob 디코드 → 캔버스)
    try {
      const arr = await blob.arrayBuffer();
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      drawWave(await audioCtx.decodeAudioData(arr));
    } catch {}

    updateSession(Number(gen), Number(aud), Number(chars), Number(rtf));
    addHistory(text, lang.value, speaker.value, rtf, curUrl);
    updateCharCount();
  } catch (e) {
    $("status").textContent = "[오류] " + e.message;
  } finally {
    running = false;
    btn.disabled = false;
  }
}
btn.addEventListener("click", generate);
q.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") generate();
});

// ── 세션 누적 + 비용 ──
function updateSession(genS, audioS, chars, rtf) {
  S.count += 1;
  S.genS += genS || 0;
  S.audioS += audioS || 0;
  S.chars += chars || 0;
  S.rtfSum += rtf || 0;

  setV("sCount", S.count);
  setV("sRtf", (S.rtfSum / S.count).toFixed(2));
  setV("sAudio", S.audioS.toFixed(0), "s");
  setV("sChars", S.chars.toLocaleString());

  if (curRate == null) {
    setV("cPerM", "—");
    setV("cReq", "—");
    return;
  }
  const reqCost = ((genS || 0) / 3600) * curRate;
  S.costS += reqCost;
  const perM = S.chars ? ((S.genS / 3600) * curRate / S.chars) * 1e6 : 0;
  setV("cPerM", Math.round(perM).toLocaleString(), "원");
  setV("cReq", reqCost.toFixed(3), "원");
}

// ── 히스토리 ──
function showHistEmpty() {
  $("hist").innerHTML = '<div class="empty" id="histEmpty">아직 생성한 음성이 없어요.</div>';
}

function addHistory(text, langId, spk, rtf, url) {
  const empty = $("histEmpty");
  if (empty) empty.remove();
  const item = document.createElement("div");
  item.className = "hitem";
  item._url = url;
  item.innerHTML =
    `<div class="play">▶</div><div class="txt"></div>` +
    `<div class="tag">${langId}·${spk} · RTF ${rtf ?? "—"}</div>` +
    `<div class="del" title="삭제">✕</div>`;
  item.querySelector(".txt").textContent = text;
  item.querySelector(".play").addEventListener("click", () => {
    $("audio").src = url;
    $("audio").play().catch(() => {});
  });
  item.querySelector(".del").addEventListener("click", () => {
    URL.revokeObjectURL(url);
    item.remove();
    if (!$("hist").querySelector(".hitem")) showHistEmpty();
  });
  $("hist").prepend(item);
}

// 모두 지우기
$("clearHist").addEventListener("click", () => {
  $("hist").querySelectorAll(".hitem").forEach((el) => {
    if (el._url) URL.revokeObjectURL(el._url);
  });
  showHistEmpty();
});

// ── 파형 시각화 ──
function drawWave(audioBuf) {
  const c = $("wave");
  if (!c) return;
  const w = c.clientWidth || 600, hgt = 72;
  c.width = w;
  c.height = hgt;
  const ctx = c.getContext("2d");
  ctx.clearRect(0, 0, w, hgt);
  const data = audioBuf.getChannelData(0);
  const step = Math.max(1, Math.floor(data.length / w));
  const mid = hgt / 2;
  ctx.fillStyle = "#a855f7";
  for (let x = 0; x < w; x++) {
    let min = 1, max = -1;
    for (let j = 0; j < step; j++) {
      const v = data[x * step + j] || 0;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    ctx.fillRect(x, mid + min * mid, 1, Math.max(1, (max - min) * mid));
  }
}

// ── 실시간 GPU 지표 + 스파크라인 ──
const MAXH = 48;
const utilHist = [];

function drawSpark() {
  const c = $("utilSpark");
  if (!c) return;
  const w = c.clientWidth || 300, hgt = 40;
  if (c.width !== w) c.width = w;
  c.height = hgt;
  const ctx = c.getContext("2d");
  ctx.clearRect(0, 0, w, hgt);
  if (utilHist.length < 2) return;
  ctx.beginPath();
  utilHist.forEach((v, i) => {
    const x = (i / (MAXH - 1)) * w;
    const y = hgt - (Math.min(100, v) / 100) * (hgt - 4) - 2;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#a855f7";
  ctx.lineWidth = 2;
  ctx.stroke();
}

async function pollGpu() {
  try {
    const g = await (await fetch("/gpu.json", { cache: "no-store" })).json();
    if (!g || !g.name) return;
    $("gpuName").textContent = g.name;
    curRate = g.rate ?? null; // 서버가 gpu.json에 실어준 요금 그대로
    $("rateLabel").textContent = curRate ? `(${curRate.toLocaleString()}원/h)` : "";

    const util = Number(g.util ?? 0), vram = Number(g.vram_used_gb ?? 0), vramT = Number(g.vram_total_gb ?? 0);
    $("utilV").textContent = util + "%";
    $("utilBar").style.width = Math.min(100, util) + "%";
    $("vramV").textContent = vram.toFixed(1) + (vramT ? " / " + vramT.toFixed(1) : "") + " GB";
    if (vramT) $("vramBar").style.width = Math.min(100, (vram / vramT) * 100) + "%";

    utilHist.push(util);
    if (utilHist.length > MAXH) utilHist.shift();
    drawSpark();
  } catch {}
}
setInterval(pollGpu, 1000);
pollGpu();
