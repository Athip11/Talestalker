/**
 * game.js - Fern Visual Novel
 * ─────────────────────────────────────────────
 * Live2D control · Flask API · BG polling
 */

"use strict";

/* ══════════════════════════════════════════
   CONFIG
══════════════════════════════════════════ */
const CONFIG = {
  AP_MAX: 100,
  TP_MAX: 100,
  LIVE2D_MODEL_PATH: "/static/live2d/fern/fern.model3.json",

  /* mood → Live2D motion group mapping */
  MOTION_MAP: {
    neutral: { motion: "fern_neutral" },
    exasperated: { motion: "fern_exasperated" },
    sad: { motion: "fern_sad" },
    happy: { motion: "fern_happy" },
    touched: { motion: "fern_touched" },
  },

  /* mood → glow color for reaction box */
  MOOD_COLOR: {
    exasperated: "#fb923c",
    touched: "#fda4af",
    happy: "#fde68a",
    neutral: "#6b9fd4",
    sad: "#7dd3fc",
  },
  BG_POLL_INTERVAL: 3000, // ms ระหว่าง poll
  BG_POLL_MAX: 60, // poll สูงสุด 60 ครั้ง (~3 นาที)
};

/* ══════════════════════════════════════════
   GAME STATE
══════════════════════════════════════════ */
// session_id คงที่ตลอด browser session
const SESSION_ID =
  sessionStorage.getItem("fern_sid") ||
  (() => {
    const id = Math.random().toString(36).slice(2, 10);
    sessionStorage.setItem("fern_sid", id);
    return id;
  })();

const state = {
  ap: 20,
  tp: 20,
  episode: "EP1",
  episodeLabel: "EP 1 · ฝนตกครั้งแรก",
  mood: "neutral",
  moodCounter: 0,
  busy: false,
  live2dModel: null,
};

/* ══════════════════════════════════════════
   DOM REFS
══════════════════════════════════════════ */
const $ = (id) => document.getElementById(id);
const DOM = {
  loading: $("loading-overlay"),
  root: $("game-root"),
  chatLog: $("chat-log"),
  input: $("player-input"),
  sendBtn: $("send-btn"),
  apBar: $("ap-bar"),
  tpBar: $("tp-bar"),
  apVal: $("ap-val"),
  tpVal: $("tp-val"),
  epLabel: $("ep-label"),
  moodDot: $("mood-dot"),
  moodText: $("mood-text"),
  moodCounter: $("mood-counter-text"),
  status: $("status-text"),
  reactionBox: $("reaction-box"),
  reactionTxt: $("reaction-text"),
  toast: $("toast"),
  toastText: $("toast-text"),
  live2dWrap: $("live2d-wrapper"),
};

/* ══════════════════════════════════════════
   LIVE2D INIT
══════════════════════════════════════════ */
async function initLive2D() {
  if (window.LIVE2D_UNAVAILABLE || !window.PIXI || !window.PIXI.live2d) {
    console.warn("Live2D libs not loaded — using placeholder.");
    showPlaceholderCharacter();
    return;
  }

  try {
    const { Live2DModel } = PIXI.live2d;

    const app = new PIXI.Application({
      width: DOM.live2dWrap.clientWidth || 400,
      height: DOM.live2dWrap.clientHeight || 600,
      backgroundAlpha: 0,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
    });
    DOM.live2dWrap.appendChild(app.view);

    window.addEventListener("resize", () => {
      app.renderer.resize(
        DOM.live2dWrap.clientWidth,
        DOM.live2dWrap.clientHeight,
      );
      if (state.live2dModel) repositionModel(app);
    });

    const model = await Live2DModel.from(CONFIG.LIVE2D_MODEL_PATH);
    app.stage.addChild(model);
    state.live2dModel = model;
    state._app = app;
    repositionModel(app);
    playMotion("fern_neutral");

    model.interactive = true;
    model.on("pointerdown", () => playMotion("Idle"));
  } catch (err) {
    console.error("Live2D init error:", err);
    showPlaceholderCharacter();
  }
}

function repositionModel(app) {
  applyViewMode(currentViewMode, app);
}

function playMotion(group, index = 0) {
  if (!state.live2dModel) return;
  try {
    state.live2dModel.motion(group, index);
  } catch (_) {}
}

function playExpression(name) {
  if (!state.live2dModel || !name) return;
  try {
    state.live2dModel.expression(name);
  } catch (_) {}
}

function applyMoodToLive2D(mood) {
  const map = CONFIG.MOTION_MAP[mood] || CONFIG.MOTION_MAP.neutral;
  playMotion(map.motion);
  if (map.expression) playExpression(map.expression);
}

function showPlaceholderCharacter() {
  DOM.live2dWrap.innerHTML = `
    <div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;">
      <div style="
        width:180px;height:280px;
        background:linear-gradient(170deg,rgba(42,82,152,0.3),rgba(10,22,40,0.5));
        border:1px solid rgba(107,159,212,0.25);
        border-radius:90px 90px 60px 60px;
        display:flex;align-items:center;justify-content:center;
        font-size:3rem;
        backdrop-filter:blur(10px);
      ">🌧️</div>
    </div>`;
}

/* ══════════════════════════════════════════
   FLASK API CALLS
══════════════════════════════════════════ */
async function apiStart(forceNew = false) {
  const res = await fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: SESSION_ID, force_new: forceNew }),
  });
  return res.json();
}

async function apiTalk(text) {
  const res = await fetch("/api/talk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, session_id: SESSION_ID }),
  });
  return res.json();
}

/* ══════════════════════════════════════════
   UI UPDATES
══════════════════════════════════════════ */
function updateStats({ ap, tp, mood, moodCounter, episodeLabel }) {
  if (ap !== undefined) {
    state.ap = ap;
    DOM.apBar.style.width = `${Math.min(100, (ap / CONFIG.AP_MAX) * 100)}%`;
    DOM.apVal.textContent = ap;
  }
  if (tp !== undefined) {
    state.tp = tp;
    DOM.tpBar.style.width = `${Math.min(100, (tp / CONFIG.TP_MAX) * 100)}%`;
    DOM.tpVal.textContent = tp;
  }
  if (mood !== undefined) {
    state.mood = mood;
    const color = CONFIG.MOOD_COLOR[mood] || "#6b9fd4";
    const MOOD_LABEL = {
      exasperated: "Exasperated",
      neutral: "Indifferent",
      sad: "Sad",
      happy: "Happy",
      touched: "Smitten",
    };
    DOM.moodDot.style.background = color;
    DOM.moodText.textContent = MOOD_LABEL[mood] || mood;
    DOM.moodText.style.color = color;
  }
  if (moodCounter !== undefined) {
    state.moodCounter = moodCounter;
    DOM.moodCounter.textContent = ""; // ซ่อน score
  }
  if (episodeLabel !== undefined) {
    DOM.epLabel.textContent = episodeLabel;
  }
}

/* ── Streaming text ── */
function streamText(el, text, speed = 22) {
  return new Promise((resolve) => {
    el.textContent = "";
    const chars = [...text];
    let i = 0;
    function tick() {
      if (i >= chars.length) {
        resolve();
        return;
      }
      el.textContent += chars[i++];
      DOM.chatLog.scrollTop = DOM.chatLog.scrollHeight;
      setTimeout(tick, speed);
    }
    tick();
  });
}

function addMessage(speaker, text, mood = "neutral", stream = false) {
  const isPlayer = speaker === "player";

  const wrapper = document.createElement("div");
  wrapper.className = `msg-bubble flex ${isPlayer ? "justify-end" : "justify-start"}`;

  if (isPlayer) {
    wrapper.innerHTML = `
      <div class="max-w-xs lg:max-w-sm px-2 py-1.5 text-sm leading-relaxed font-thai">
        <span style="color:#f9a8d4;font-weight:600">Player : </span>
        <span style="color:rgba(220,230,245,0.85)">${escHtml(text)}</span>
      </div>`;
    DOM.chatLog.appendChild(wrapper);
    DOM.chatLog.scrollTop = DOM.chatLog.scrollHeight;
    return Promise.resolve();
  }

  wrapper.innerHTML = `
    <div class="flex gap-2.5 max-w-xs lg:max-w-sm">
      <div class="px-3 py-2.5 text-sm leading-relaxed font-thai" style="color:#e2eaf5">
        <span style="color:#c084fc;font-weight:600">Fern : </span>
        <span class="msg-body"></span>
      </div>
    </div>`;
  DOM.chatLog.appendChild(wrapper);
  DOM.chatLog.scrollTop = DOM.chatLog.scrollHeight;

  const bodyEl = wrapper.querySelector(".msg-body");
  return stream
    ? streamText(bodyEl, text)
    : ((bodyEl.textContent = text), Promise.resolve());
}

function addSystemMessage(text, color = "#6b9fd4", stream = false) {
  const el = document.createElement("div");
  el.className = "msg-bubble text-center text-xs py-2 font-thai";
  el.style.color = color;

  if (stream) {
    const inner = document.createElement("span");
    inner.style.cssText = `border-bottom:1px dashed ${color}40;padding-bottom:2px`;
    el.appendChild(inner);
    DOM.chatLog.appendChild(el);
    DOM.chatLog.scrollTop = DOM.chatLog.scrollHeight;
    return streamText(inner, ` ${text} `, 18);
  }

  el.innerHTML = `<span style="border-bottom:1px dashed ${color}40;padding-bottom:2px"> ${escHtml(text)} </span>`;
  DOM.chatLog.appendChild(el);
  DOM.chatLog.scrollTop = DOM.chatLog.scrollHeight;
  return Promise.resolve();
}

function showToast(text, duration = 3000) {
  DOM.toastText.textContent = text;
  DOM.toast.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(
    () => DOM.toast.classList.add("hidden"),
    duration,
  );
}

function setStatus(text) {
  DOM.status.textContent = text;
}

function setBusy(busy) {
  state.busy = busy;
  DOM.sendBtn.disabled = busy;
  DOM.input.disabled = busy;
  DOM.sendBtn.style.opacity = busy ? "0.5" : "1";
  setStatus(busy ? "ฝนกำลังตอบ..." : "พิมพ์ข้อความถึงฝน");
}

function shakeScreen() {
  DOM.root.classList.remove("shake");
  void DOM.root.offsetWidth;
  DOM.root.classList.add("shake");
  setTimeout(() => DOM.root.classList.remove("shake"), 400);
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br>");
}

/* ══════════════════════════════════════════
   ENDING SCREEN
══════════════════════════════════════════ */
const ENDING_DATA = {
  warm_a: {
    emoji: "❤️",
    title: "ฝนหยุดแล้ว",
    color: "#fda4af",
    desc: "เธอหยุดรอ และเธอรู้ว่าใครบางคนจะอยู่ตรงนั้นเสมอ",
  },
  warm_b: {
    emoji: "💛",
    title: "ใต้ร่มคันเดียวกัน",
    color: "#fde68a",
    desc: "ไม่ต้องพูดอะไรมาก แค่เดินไปด้วยกัน",
  },
  warm_c: {
    emoji: "🌱",
    title: "เพื่อนที่ดีที่สุด",
    color: "#86efac",
    desc: "บางความสัมพันธ์ไม่ต้องการคำนิยาม",
  },
  cold_a: {
    emoji: "🌤️",
    title: "รอยยิ้มสุดท้าย",
    color: "#7dd3fc",
    desc: "เธอยิ้มให้ครั้งสุดท้ายก่อนจะหันหลังเดินไป",
  },
  cold_b: {
    emoji: "🌧️",
    title: "ฝนที่ไม่หยุด",
    color: "#93c5fd",
    desc: "บางครั้งฝนก็ตกโดยไม่มีสัญญาณว่าจะหยุด",
  },
  cold_c: {
    emoji: "💔",
    title: "ใจสลาย",
    color: "#f87171",
    desc: "มีบางอย่างที่หักไปแล้วจะซ่อมไม่ได้",
  },
};

function showEnding(endingKey) {
  const data = ENDING_DATA[endingKey] || {
    emoji: "🌸",
    title: endingKey,
    color: "#c8dff5",
    desc: "จบแล้ว",
  };

  const overlay = document.createElement("div");
  overlay.style.cssText = `
    position:fixed;inset:0;z-index:90;
    background:rgba(5,13,26,0.92);
    display:flex;flex-direction:column;
    align-items:center;justify-content:center;
    gap:1.5rem;
    animation:fadeIn 1s ease forwards;
  `;
  overlay.innerHTML = `
    <div style="font-size:4rem;animation:glowPulse 2s ease-in-out infinite">${data.emoji}</div>
    <div style="font-family:'Playfair Display',serif;font-style:italic;font-size:2rem;color:${data.color}">
      ${data.title}
    </div>
    <p style="font-family:'Sarabun',sans-serif;font-size:0.95rem;color:rgba(200,223,245,0.7);
              max-width:320px;text-align:center;line-height:1.8">
      ${data.desc}
    </p>
    <div style="margin-top:1rem;display:flex;gap:0.75rem">
      <button id="replay-btn"
        style="font-family:'Sarabun',sans-serif;
               padding:0.6rem 1.6rem;border-radius:999px;
               background:rgba(42,82,152,0.5);
               border:1px solid rgba(107,159,212,0.35);
               color:#c8dff5;font-size:0.875rem;cursor:pointer;">
        เล่นใหม่
      </button>
    </div>`;
  document.body.appendChild(overlay);

  // เล่นใหม่: สร้าง session ใหม่แทน reload
  overlay.querySelector("#replay-btn").addEventListener("click", () => {
    overlay.remove();
    sessionStorage.removeItem("fon_sid");
    location.reload();
  });
}

/* ── Wait-for-tap helper ── */
function waitForTap() {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.style.cssText = [
      "position:fixed",
      "inset:0",
      "z-index:60",
      "display:flex",
      "align-items:flex-end",
      "justify-content:center",
      "padding-bottom:calc(var(--panel-h,260px) + 20px)",
      "cursor:pointer",
    ].join(";");
    overlay.innerHTML = `<span style="
      font-family:'Sarabun',sans-serif;font-size:0.72rem;
      color:rgba(200,220,245,0.55);letter-spacing:0.18em;
      animation:tapBlink 1.4s ease-in-out infinite;
    ">▼ แตะเพื่อดำเนินการต่อ ▼</span>`;
    document.body.appendChild(overlay);
    overlay.addEventListener(
      "pointerdown",
      () => {
        overlay.remove();
        resolve();
      },
      { once: true },
    );
  });
}

/* ══════════════════════════════════════════
   SEND MESSAGE FLOW
══════════════════════════════════════════ */
async function handleSend() {
  if (state.busy) return;

  const text = DOM.input.value.trim();
  if (!text) return;

  DOM.input.value = "";
  DOM.input.style.height = "auto";
  addMessage("player", text);
  setBusy(true);

  try {
    const res = await apiTalk(text);

    updateStats({
      ap: res.ap,
      tp: res.tp,
      mood: res.mood,
      moodCounter: res.mood_counter,
      episodeLabel: res.episode_label,
    });

    applyMoodToLive2D(res.mood);

    if (res.ap_change < -4 || res.tp_change < -4) shakeScreen();

    await addMessage("fon", res.reaction, res.mood, true);

    const apSign = res.ap_change >= 0 ? `+${res.ap_change}` : res.ap_change;
    const tpSign = res.tp_change >= 0 ? `+${res.tp_change}` : res.tp_change;
    if (res.ap_change !== 0 || res.tp_change !== 0) {
      showToast(`AP ${apSign}  ·  TP ${tpSign}`, 2500);
    }

    /* ── Episode change ── */
    if (res.episode && res.episode !== state.episode) {
      state.episode = res.episode;

      await waitForTap();
      DOM.chatLog.innerHTML = "";

      addSystemMessage(res.episode_label || res.episode, "#fde68a");
      if (res.bg_prompt) loadBackground(res.bg_prompt);

      if (res.new_ep_context)
        await addSystemMessage(res.new_ep_context, "#64748b", true);
      if (res.new_ep_narrative)
        await addSystemMessage(res.new_ep_narrative, "#94a3b8", true);
      if (res.new_ep_hint) addSystemMessage("💡 " + res.new_ep_hint, "#fde68a");
      if (res.new_ep_intro)
        await addMessage("fon", res.new_ep_intro, res.mood, true);
    }

    /* ── Ending ── */
    if (res.event === "ending") {
      if (res.ending === "warm_a") applyMoodToLive2D("happy");
      else if (res.ending === "cold_c") applyMoodToLive2D("sad");
      setTimeout(() => showEnding(res.ending), 1200);
    }
  } catch (err) {
    console.error("apiTalk error:", err);
    addSystemMessage("เกิดข้อผิดพลาด กรุณาลองใหม่", "#f87171");
    setStatus("เกิดข้อผิดพลาด");
  } finally {
    setBusy(false);
    DOM.input.focus();
  }
}

/* ══════════════════════════════════════════
   BACKGROUND GENERATION  (พร้อม poll loop)
══════════════════════════════════════════ */
let currentBgPrompt = null;

function applyBgGradient(prompt) {
  const bgEl = document.getElementById("game-bg");
  if (!bgEl) return;
  const p = (prompt || "").toLowerCase();
  let grad;
  if (p.includes("cafe") || p.includes("warm"))
    grad = "linear-gradient(160deg,#1a120a 0%,#0d0806 100%)";
  else if (p.includes("river") || p.includes("sunset"))
    grad = "linear-gradient(160deg,#0d1a1a 0%,#060d0a 100%)";
  else if (p.includes("night") || p.includes("train"))
    grad = "linear-gradient(160deg,#080c1a 0%,#04060f 100%)";
  else if (p.includes("rooftop") || p.includes("city"))
    grad = "linear-gradient(160deg,#0a0c18 0%,#050610 100%)";
  else grad = "linear-gradient(160deg,#0e1a30 0%,#050d18 100%)";
  bgEl.style.backgroundImage = grad;
}

function applyBgImage(dataUrl) {
  const bgEl = document.getElementById("game-bg");
  if (!bgEl) return;
  bgEl.style.transition = "opacity 0.9s ease";
  bgEl.style.backgroundImage = `url(${dataUrl})`;
  bgEl.style.backgroundSize = "cover";
  bgEl.style.backgroundPosition = "center";
}

async function pollBgJob(jobId) {
  for (let i = 0; i < CONFIG.BG_POLL_MAX; i++) {
    await new Promise((r) => setTimeout(r, CONFIG.BG_POLL_INTERVAL));
    try {
      const res = await fetch(`/api/bg/status/${jobId}`);
      const data = await res.json();

      if (data.status === "done") {
        if (data.image) applyBgImage(data.image);
        setStatus("พิมพ์ข้อความถึงฝน");
        return;
      }
      if (data.status === "error" || data.status === "not_found") {
        console.warn("BG job failed:", data.status);
        setStatus("พิมพ์ข้อความถึงฝน");
        return;
      }
      // status === "pending" → loop ต่อ
    } catch (err) {
      console.warn("BG poll error:", err.message);
      setStatus("พิมพ์ข้อความถึงฝน");
      return;
    }
  }
  // หมดรอบ poll
  console.warn("BG job timed out after polling");
  setStatus("พิมพ์ข้อความถึงฝน");
}

async function loadBackground(prompt) {
  if (!prompt || prompt === currentBgPrompt) return;
  currentBgPrompt = prompt;

  applyBgGradient(prompt); // แสดง gradient ทันทีก่อนรอ GPU
  setStatus("กำลังโหลดฉาก...");

  try {
    const res = await fetch("/api/bg", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });

    if (!res.ok) {
      console.warn("BG request error:", res.status);
      setStatus("พิมพ์ข้อความถึงฝน");
      return;
    }

    const data = await res.json();
    if (data.job_id) {
      // poll จนกว่า GPU จะเสร็จ
      pollBgJob(data.job_id); // ไม่ await — รันใน background
    }
  } catch (err) {
    console.warn("BG failed:", err.message);
    setStatus("พิมพ์ข้อความถึงฝน");
  }
}

/* ══════════════════════════════════════════
   INPUT EVENT WIRING
══════════════════════════════════════════ */
DOM.sendBtn.addEventListener("click", handleSend);

DOM.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

DOM.input.addEventListener("input", () => {
  DOM.input.style.height = "auto";
  DOM.input.style.height = Math.min(DOM.input.scrollHeight, 96) + "px";
});

/* ══════════════════════════════════════════
   VIEW MODE — fullbody / half / closeup
══════════════════════════════════════════ */
const VIEW_MODES = {
  fullbody: { scale: 1.2, label: "Full" },
  half: { scale: 3.0, label: "Half" },
  closeup: { scale: 4.5, label: "Close-up" },
};
let currentViewMode = "fullbody";

function applyViewMode(mode, app) {
  if (!state.live2dModel) return;
  currentViewMode = mode;
  const m = state.live2dModel;
  const W = DOM.live2dWrap.clientWidth || app.renderer.width;
  const H = DOM.live2dWrap.clientHeight || app.renderer.height;
  const origW = m.internalModel.originalWidth;
  const origH = m.internalModel.originalHeight;
  const mult = VIEW_MODES[mode].scale;
  const scale = Math.min((W / origW) * mult, (H / origH) * mult);
  m.scale.set(scale);
  m.x = (W - origW * scale) / 2;
  if (mode === "half") m.y = H * 0.2;
  else if (mode === "closeup") m.y = H * 0.1;
  else m.y = H * 0.25;
}

document.querySelectorAll("#view-radio input[type=radio]").forEach((radio) => {
  radio.addEventListener("change", () => {
    if (radio.checked && state._app) applyViewMode(radio.value, state._app);
  });
});

/* ══════════════════════════════════════════
   BOOT SEQUENCE
══════════════════════════════════════════ */
async function boot() {
  initLive2D();

  // ถ้า game_over ค้างจาก session ก่อน → force สร้างใหม่
  const isReturning = sessionStorage.getItem("fon_sid") !== null;

  try {
    const startData = await apiStart(false);

    // ถ้า session เดิม game_over แล้ว server จะส่ง error → สร้างใหม่
    if (startData.error) {
      const freshData = await apiStart(true);
      return bootWithData(freshData);
    }

    bootWithData(startData);
  } catch (err) {
    console.error("Boot error:", err);
    DOM.loading.classList.add("hidden");
    DOM.root.style.opacity = "1";
    addSystemMessage("ไม่สามารถเชื่อมต่อ server ได้", "#f87171");
  }
}

async function bootWithData(startData) {
  if (startData.episode) state.episode = startData.episode;
  updateStats({
    ap: startData.ap ?? 20,
    tp: startData.tp ?? 20,
    mood: "neutral",
    moodCounter: 0,
    episodeLabel: startData.episode_label ?? "EP 1",
  });

  if (startData.bg_prompt) loadBackground(startData.bg_prompt);

  DOM.loading.classList.add("hidden");
  DOM.root.style.opacity = "1";
  DOM.input.focus();

  if (startData.context)
    await addSystemMessage(startData.context, "#64748b", true);
  if (startData.narrative)
    await addSystemMessage(startData.narrative, "#94a3b8", true);
  if (startData.hint) addSystemMessage(`💡 ${startData.hint}`, "#fde68a");
  if (startData.intro_text)
    await addMessage("fon", startData.intro_text, "neutral", true);
}

/* ══════════════════════════════════════════
   KICK OFF
══════════════════════════════════════════ */
window.addEventListener("DOMContentLoaded", boot);
