/**
 * game.js - Fern Visual Novel
 * ─────────────────────────────────────────────
 * Live2D control · Flask API · BG polling
 */

"use strict";

/* ══════════════════════════════════════════
   SUPABASE AUTH
══════════════════════════════════════════ */
const SUPABASE_URL = "https://vmssbldsyrayluhdlfcy.supabase.co"; // ← ใส่ของจริง
const SUPABASE_ANON_KEY = "sb_publishable_TIv965QLMmOiYfA71UUarg_vMacvbxx"; // ← ใส่ของจริง

const _supabase = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

let _accessToken = null; // เก็บ JWT ปัจจุบัน
let _username = null; // เก็บ username ของผู้เล่น (โหลดจาก /api/profile)

/* ── Login UI helpers ── */
function showLoginMsg(msg, color = "#f87171") {
  document.getElementById("login-msg").style.color = color;
  document.getElementById("login-msg").textContent = msg;
}

function hideLoginScreen() {
  document.getElementById("login-screen").style.display = "none";
}

/* ── Google Login ── */
document.getElementById("google-btn").addEventListener("click", async () => {
  const { error } = await _supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: window.location.origin },
  });
  if (error) showLoginMsg(error.message);
});

/* ── Discord Login ── */
document.getElementById("discord-btn").addEventListener("click", async () => {
  const btn = document.getElementById("discord-btn");
  btn.disabled = true;
  btn.textContent = "กำลังเชื่อมต่อ...";
  const { error } = await _supabase.auth.signInWithOAuth({
    provider: "discord",
    options: { redirectTo: window.location.origin },
  });
  if (error) {
    showLoginMsg(error.message);
    btn.disabled = false;
    btn.textContent = "เข้าสู่ระบบด้วย Discord";
  }
});

/* ── Email OTP ── */
let _otpEmail = "";
document.getElementById("email-input").addEventListener("input", (e) => {
  _otpEmail = e.target.value.trim();
});

document.getElementById("otp-send-btn").addEventListener("click", async () => {
  const email = document.getElementById("email-input").value.trim();
  if (!email) {
    showLoginMsg("กรุณากรอกอีเมล");
    return;
  }

  showLoginMsg("กำลังส่ง OTP...", "#fde68a");
  const { error } = await _supabase.auth.signInWithOtp({ email });
  if (error) {
    showLoginMsg(error.message);
  } else {
    document.getElementById("email-step").style.display = "none";
    document.getElementById("otp-step").style.display = "flex";
    showLoginMsg("ส่ง OTP แล้ว ตรวจสอบอีเมลของคุณ", "#86efac");
  }
});

document
  .getElementById("otp-verify-btn")
  .addEventListener("click", async () => {
    const otp = document.getElementById("otp-input").value.trim();
    if (otp.length !== 6) {
      showLoginMsg("OTP ต้องมี 6 หลัก");
      return;
    }

    showLoginMsg("กำลังยืนยัน...", "#fde68a");
    const { data, error } = await _supabase.auth.verifyOtp({
      email: _otpEmail,
      token: otp,
      type: "email",
    });
    if (error) {
      showLoginMsg("OTP ไม่ถูกต้องหรือหมดอายุ");
    } else {
      _accessToken = data.session.access_token;
      _booted = true;
      hideLoginScreen();
      checkProfile();
    }
  });

/* ── Session restore (Google redirect / existing session) ── */
let _booted = false; // กันไม่ให้ boot() ถูกเรียกซ้ำ

async function initAuth() {
  // ซ่อน loading overlay ระหว่างรอเช็ค session — จะแสดงใหม่ใน bootWithData
  document.getElementById("loading-overlay").classList.add("hidden");

  const {
    data: { session },
  } = await _supabase.auth.getSession();

  if (session && !_booted) {
    _booted = true;
    _accessToken = session.access_token;
    hideLoginScreen();
    checkProfile();
  }
  // ถ้าไม่มี session → login screen แสดงอยู่แล้วโดย default
}

// Refresh token อัตโนมัติ (ไม่ boot ซ้ำ)
_supabase.auth.onAuthStateChange((event, session) => {
  if (session) _accessToken = session.access_token;
});

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
};

/* ══════════════════════════════════════════
   GAME STATE
══════════════════════════════════════════ */
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

function applyMoodToLive2D(mood) {
  const map = CONFIG.MOTION_MAP[mood] || CONFIG.MOTION_MAP.neutral;
  playMotion(map.motion);
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
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${_accessToken}`,
    },
    body: JSON.stringify({ force_new: forceNew }),
  });
  return res.json();
}

async function apiTalk(text) {
  const res = await fetch("/api/talk", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${_accessToken}`,
    },
    body: JSON.stringify({ text, username: _username || "ผู้เล่น" }),
  });
  return res.json();
}

async function apiGetProfile() {
  const res = await fetch("/api/profile", {
    headers: { Authorization: `Bearer ${_accessToken}` },
  });
  return res.json();
}

async function apiSetProfile(username) {
  const res = await fetch("/api/profile", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${_accessToken}`,
    },
    body: JSON.stringify({ username }),
  });
  return res.json();
}

async function apiGetSettings() {
  const res = await fetch("/api/settings", {
    headers: { Authorization: `Bearer ${_accessToken}` },
  });
  return res.json();
}

async function apiSetSettings(provider) {
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${_accessToken}`,
    },
    body: JSON.stringify({ llm_provider: provider }),
  });
  return res.json();
}

/* ── LLM provider state ── */
let _llmProvider = "gemini";

function setLlmProvider(provider) {
  _llmProvider = provider;
  document.querySelectorAll(".llm-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.llm === provider);
  });
  const badge = document.getElementById("llm-badge");
  if (badge) {
    badge.textContent = provider === "typhoon" ? "Typhoon" : "Gemini";
    badge.classList.toggle("typhoon", provider === "typhoon");
  }
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
      neutral: "Neutral",
      sad: "Sad",
      happy: "Happy",
      touched: "Touched",
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

  if (isPlayer) {
    const displayName = _username || "Player";
    const nameColor = "#93c5fd"; // blue for player
    const wrapper = document.createElement("div");
    wrapper.className = "msg-row-player";
    wrapper.innerHTML = `
      <div class="player-msg-wrap">
        <div class="player-name-tag" style="color:${nameColor}">${escHtml(displayName)}</div>
        <div class="player-bubble">${escHtml(text)}</div>
      </div>`;
    DOM.chatLog.appendChild(wrapper);
    DOM.chatLog.scrollTop = DOM.chatLog.scrollHeight;
    return Promise.resolve();
  }

  // Fern
  const wrapper = document.createElement("div");
  wrapper.className = "msg-row-fern";
  wrapper.innerHTML = `
    <div class="fern-msg-wrap">
      <div class="fern-name-tag">เฟิร์น</div>
      <div class="fern-bubble"><span class="msg-body"></span></div>
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
  setStatus(busy ? "เฟิร์นกำลังตอบ..." : "พิมพ์ข้อความถึงเฟิร์น");
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

function showEnding(
  endingKey,
  endingTitle,
  endingText,
  endingSetting,
  endingMood,
) {
  const data = ENDING_DATA[endingKey] || {
    emoji: "🌸",
    title: endingKey,
    color: "#c8dff5",
    desc: "จบแล้ว",
  };

  const displayTitle = endingTitle || data.title;
  const storyHtml = endingText ? endingText.replace(/\n/g, "<br>") : data.desc;
  const playerName = _username || "ผู้เล่น";

  const overlay = document.createElement("div");
  overlay.style.cssText = `
    position:fixed;inset:0;z-index:90;
    background:rgba(5,13,26,0.92);
    display:flex;flex-direction:column;
    align-items:center;justify-content:center;
    gap:1.5rem;padding:2rem;
    animation:fadeIn 1s ease forwards;
    overflow-y:auto;
  `;

  overlay.innerHTML = `
    <div style="font-size:4rem;animation:glowPulse 2s ease-in-out infinite">${data.emoji}</div>
    <div style="font-family:'Playfair Display',serif;font-style:italic;font-size:1.8rem;
                color:${data.color};text-align:center">${displayTitle}</div>
    <p style="font-family:'Sarabun',sans-serif;font-size:0.92rem;
              color:rgba(200,223,245,0.75);max-width:320px;text-align:center;line-height:2">
      ${storyHtml}
    </p>

    <!-- ─── Gift Section ─── -->
    <div id="gift-section" style="
      width:100%;max-width:340px;
      background:rgba(255,255,255,0.04);
      border:1px solid rgba(200,223,245,0.15);
      border-radius:16px;padding:1.25rem 1rem;
      display:flex;flex-direction:column;align-items:center;gap:0.75rem;
    ">
      <p style="font-family:'Sarabun',sans-serif;font-size:0.88rem;
                color:rgba(200,223,245,0.85);text-align:center;line-height:1.7;margin:0">
        <span style="color:${data.color};font-weight:600">${escHtmlSimple(playerName)}</span>
        จะให้ของขวัญอะไรกับเฟิร์นก่อนลาจากกันไหม?
      </p>
      <div style="display:flex;gap:0.5rem;width:100%">
        <input id="gift-input" type="text" maxlength="50"
          placeholder="เช่น ดอกไม้ป่า, ขนมหวาน, หนังสือเวท..."
          style="flex:1;padding:0.55rem 0.85rem;border-radius:10px;border:1px solid rgba(200,223,245,0.2);
                 background:rgba(255,255,255,0.06);color:#e2e8f0;
                 font-family:'Sarabun',sans-serif;font-size:0.85rem;outline:none;"/>
        <button id="gift-send-btn"
          style="padding:0.55rem 1rem;border-radius:10px;border:none;
                 background:rgba(42,82,152,0.6);color:#c8dff5;
                 font-family:'Sarabun',sans-serif;font-size:0.85rem;cursor:pointer;
                 white-space:nowrap;">
          มอบให้
        </button>
      </div>
      <div id="gift-status" style="font-size:0.78rem;color:rgba(200,223,245,0.5);min-height:1rem"></div>
      <div id="gift-img-wrap" style="width:100%;display:none">
        <img id="gift-img" src="" alt="gift" style="
          width:100%;border-radius:12px;
          box-shadow:0 0 24px rgba(200,223,245,0.15);
          animation:fadeIn 0.8s ease;
        "/>
        <p id="gift-caption" style="
          font-family:'Sarabun',sans-serif;font-size:0.8rem;
          color:rgba(200,223,245,0.55);text-align:center;margin-top:0.5rem;
        "></p>
      </div>
    </div>

    <!-- ─── Replay Button ─── -->
    <button id="replay-btn"
      style="font-family:'Sarabun',sans-serif;
             padding:0.6rem 1.6rem;border-radius:999px;
             background:rgba(42,82,152,0.5);
             border:1px solid rgba(107,159,212,0.35);
             color:#c8dff5;font-size:0.875rem;cursor:pointer;">
      เล่นใหม่
    </button>
  `;

  document.body.appendChild(overlay);

  /* ── Gift submit ── */
  const giftInput = overlay.querySelector("#gift-input");
  const giftSendBtn = overlay.querySelector("#gift-send-btn");
  const giftStatus = overlay.querySelector("#gift-status");
  const giftImgWrap = overlay.querySelector("#gift-img-wrap");
  const giftImg = overlay.querySelector("#gift-img");
  const giftCaption = overlay.querySelector("#gift-caption");

  async function submitGift() {
    const obj = giftInput.value.trim();
    if (!obj) {
      giftStatus.textContent = "พิมพ์ชื่อของขวัญก่อนนะคะ";
      return;
    }

    giftSendBtn.disabled = true;
    giftInput.disabled = true;
    giftStatus.textContent = "✨ กำลังสร้างภาพ...";

    try {
      const res = await fetch("/api/gift", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${_accessToken}`,
        },
        body: JSON.stringify({
          object: obj,
          mood: endingMood || "neutral",
          setting: endingSetting,
        }),
      });
      const data = await res.json();

      if (data.error) {
        giftStatus.textContent = `เกิดข้อผิดพลาด: ${data.error}`;
        giftSendBtn.disabled = false;
        giftInput.disabled = false;
        return;
      }

      giftImg.src = data.image;
      giftCaption.textContent = `"${obj}" — ของขวัญจาก ${playerName}`;
      giftImgWrap.style.display = "block";
      giftStatus.textContent = "";
      giftSendBtn.style.display = "none";
      giftInput.style.display = "none";
    } catch (err) {
      giftStatus.textContent = "ไม่สามารถเชื่อมต่อได้ กรุณาลองใหม่";
      giftSendBtn.disabled = false;
      giftInput.disabled = false;
    }
  }

  giftSendBtn.addEventListener("click", submitGift);
  giftInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitGift();
  });

  /* ── Replay ── */
  overlay.querySelector("#replay-btn").addEventListener("click", async () => {
    overlay.remove();
    sessionStorage.removeItem("fern_sid");
    DOM.chatLog.innerHTML = `<div style="text-align:center;font-size:0.68rem;
      color:rgba(255,255,255,0.18);padding:6px 0;letter-spacing:0.12em">
      ✦ เริ่มต้นการสนทนา ✦</div>`;
    DOM.loading.classList.remove("hidden");
    DOM.root.style.opacity = "0";
    try {
      const freshData = await apiStart(true);
      bootWithData(freshData);
    } catch (e) {
      console.error("restart error:", e);
      location.reload();
    }
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

    await addMessage("fern", res.reaction, res.mood, true);

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
      if (res.new_ep_hint) showHintChips(res.new_ep_hint);
      if (res.new_ep_intro)
        await addMessage("fern", res.new_ep_intro, res.mood, true);
    }

    /* ── Ending ── */
    if (res.event === "ending") {
      if (res.ending === "warm_a") applyMoodToLive2D("happy");
      else if (res.ending === "cold_c") applyMoodToLive2D("sad");
      setTimeout(
        () =>
          showEnding(
            res.ending,
            res.ending_title,
            res.ending_text,
            res.ending_setting || "",
            state.mood,
          ),
        1200,
      );
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
      setStatus("พิมพ์ข้อความถึงเฟิร์น");
      return;
    }

    const data = await res.json();
    if (data.image) {
      applyBgImage(data.image);
      console.log("[BG] ✅ โหลดภาพสำเร็จ");
    } else {
      console.warn("[BG] ไม่ได้รับ image จาก server");
    }
    setStatus("พิมพ์ข้อความถึงเฟิร์น");
  } catch (err) {
    console.warn("[BG] failed:", err.message);
    setStatus("พิมพ์ข้อความถึงเฟิร์น");
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

// NOTE: DOM.input "input" event wired in showHintChips section below

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

/* ══════════════════════════════════════════
   HUD POPUPS — camera + settings
══════════════════════════════════════════ */
(function setupHudPopups() {
  const backdrop = document.getElementById("hud-backdrop");
  const cameraBtn = document.getElementById("camera-btn");
  const settingsBtn = document.getElementById("settings-btn");
  const cameraPopup = document.getElementById("camera-popup");
  const settingsPopup = document.getElementById("settings-popup");

  function closeAll() {
    cameraPopup.classList.add("hidden");
    settingsPopup.classList.add("hidden");
    cameraBtn.classList.remove("active");
    settingsBtn.classList.remove("active");
    backdrop.classList.remove("active");
  }

  function toggle(popup, btn) {
    const isOpen = !popup.classList.contains("hidden");
    closeAll();
    if (!isOpen) {
      popup.classList.remove("hidden");
      btn.classList.add("active");
      backdrop.classList.add("active");
    }
  }

  cameraBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle(cameraPopup, cameraBtn);
  });
  settingsBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle(settingsPopup, settingsBtn);
  });
  backdrop.addEventListener("click", closeAll);

  // LLM provider buttons inside settings popup
  document.querySelectorAll(".llm-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const provider = btn.dataset.llm;
      if (provider === _llmProvider) return;
      setLlmProvider(provider);
      try {
        await apiSetSettings(provider);
        const label = provider === "gemini" ? "Gemini ✦" : "Typhoon 🌪️";
        showToast(`AI: ${label}`);
        if (DOM.status) DOM.status.textContent = `AI Model: ${label}`;
      } catch (e) {
        console.error("setSettings error:", e);
      }
      closeAll();
    });
  });

  // View mode buttons inside camera popup
  cameraPopup.querySelectorAll(".view-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      cameraPopup
        .querySelectorAll(".view-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      if (state._app) applyViewMode(btn.dataset.mode, state._app);
      closeAll();
    });
  });
})();

/* ── Logout ── */
function logout() {
  _supabase.auth.signOut().then(() => {
    _accessToken = null;
    _booted = false;
    location.reload();
  });
}
document.getElementById("logout-btn").addEventListener("click", logout);

/* ══════════════════════════════════════════
   USERNAME SCREEN
══════════════════════════════════════════ */

/**
 * checkProfile() — เรียกหลัง login สำเร็จเสมอ
 * ถ้ามี username อยู่แล้ว → boot() เลย
 * ถ้าไม่มี            → แสดง #username-screen ก่อน
 */
async function checkProfile() {
  try {
    const data = await apiGetProfile();
    const isRealUsername = data.username && !data.username.startsWith("_tmp_");
    if (isRealUsername) {
      _username = data.username;
      document.getElementById("loading-overlay").classList.remove("hidden");
      boot();
    } else {
      showUsernameScreen();
    }
  } catch (err) {
    console.error("checkProfile error:", err);
    // fallback: เข้าเกมโดยไม่มี username
    document.getElementById("loading-overlay").classList.remove("hidden");
    boot();
  }
}

function showUsernameScreen() {
  document.getElementById("username-screen").style.display = "block";

  const input = document.getElementById("username-input");
  const counter = document.getElementById("un-char-count");
  const counterWrap = input
    .closest(".ls-form-group")
    .querySelector(".un-char-counter");
  const confirmBtn = document.getElementById("username-confirm-btn");
  const randomizeBtn = document.getElementById("randomize-btn");

  // Random Thai-flavored names pool
  const RANDOM_NAMES = [
    "ดาวพระศุกร์",
    "มณีแดง",
    "ลมฝน",
    "หิมะ",
    "ทิพย์",
    "ดาว",
    "จันทร์",
    "ฟ้า",
    "น้ำฝน",
    "พลอย",
    "ปาน",
    "มิ้น",
    "ไอซ์",
    "มาย",
    "นุ้ย",
    "บิ๊ก",
    "เนม",
    "ไมค์",
    "โบ",
    "แพร",
    "แก้ว",
    "กุ้ง",
    "ปู",
    "บีม",
    "เอิ้น",
  ];

  // Disabled state — enable only when input >= 2 chars
  function updateBtnState() {
    const len = input.value.trim().length;
    confirmBtn.disabled = len < 2;
  }

  input.addEventListener("input", () => {
    const len = input.value.length;
    counter.textContent = len;
    counterWrap.classList.toggle("warn", len >= 16);
    updateBtnState();
  });

  // Randomize button
  randomizeBtn.addEventListener("click", () => {
    const name = RANDOM_NAMES[Math.floor(Math.random() * RANDOM_NAMES.length)];
    input.value = name;
    counter.textContent = name.length;
    counterWrap.classList.toggle("warn", name.length >= 16);
    updateBtnState();
    input.focus();
  });

  // Enter key
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !confirmBtn.disabled) {
      e.preventDefault();
      showUsernameConfirmModal(input.value.trim());
    }
  });

  document
    .getElementById("username-confirm-btn")
    .addEventListener("click", () => {
      if (!confirmBtn.disabled) showUsernameConfirmModal(input.value.trim());
    });

  // focus หลัง render
  setTimeout(() => input.focus(), 80);
}

/* ── Confirmation modal ── */
function showUsernameConfirmModal(username) {
  if (!username) return;

  // faux-viewport overlay (ไม่ใช้ position:fixed)
  const overlay = document.createElement("div");
  overlay.style.cssText = [
    "position:fixed",
    "inset:0",
    "z-index:200",
    "background:rgba(0,0,0,0.45)",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "padding:24px",
  ].join(";");

  overlay.innerHTML = `
    <div style="background:#fff;border-radius:16px;padding:24px 22px;max-width:320px;width:100%;font-family:Sarabun,sans-serif;">
      <p style="font-size:0.85rem;color:#6b7280;margin-bottom:10px;text-align:center">ยืนยันชื่อตัวละคร</p>
      <p style="font-size:1.4rem;font-weight:600;color:#0f1523;text-align:center;margin-bottom:8px">"${escHtmlSimple(username)}"</p>
      <p style="font-size:0.78rem;color:#d97706;text-align:center;margin-bottom:20px;line-height:1.5;background:#fffbeb;border-radius:8px;padding:8px 10px;">
        ชื่อนี้ไม่สามารถเปลี่ยนได้ภายหลัง
      </p>
      <div style="display:flex;gap:10px">
        <button id="modal-cancel" style="flex:1;padding:11px;border-radius:10px;border:1.5px solid #d1d5db;background:#fff;color:#374151;font-family:Sarabun,sans-serif;font-size:0.9rem;cursor:pointer;">แก้ไข</button>
        <button id="modal-confirm" style="flex:1;padding:11px;border-radius:10px;border:none;background:#2563eb;color:#fff;font-family:Sarabun,sans-serif;font-size:0.9rem;font-weight:600;cursor:pointer;">ยืนยัน</button>
      </div>
    </div>`;

  document.body.appendChild(overlay);

  overlay
    .querySelector("#modal-cancel")
    .addEventListener("click", () => overlay.remove());
  overlay.querySelector("#modal-confirm").addEventListener("click", () => {
    overlay.remove();
    handleUsernameConfirm(username);
  });
}

function escHtmlSimple(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function handleUsernameConfirm(username) {
  const input = document.getElementById("username-input");
  const errorEl = document.getElementById("username-error");
  const btn = document.getElementById("username-confirm-btn");
  if (!username) username = input.value.trim();

  // reset error
  errorEl.style.display = "none";
  errorEl.textContent = "";

  if (!username) {
    errorEl.textContent = "กรุณาใส่ชื่อก่อนนะคะ";
    errorEl.style.display = "block";
    return;
  }

  btn.disabled = true;
  btn.textContent = "กำลังบันทึก...";

  try {
    const data = await apiSetProfile(username);

    if (data.error) {
      errorEl.textContent =
        data.error === "username นี้ถูกใช้แล้ว"
          ? "ชื่อนี้มีคนใช้แล้วค่ะ ลองชื่ออื่นดูนะคะ"
          : data.error;
      errorEl.style.display = "block";
      btn.disabled = false;
      btn.textContent = "เริ่มการเดินทาง";
      return;
    }

    _username = data.username;
    document.getElementById("username-screen").style.display = "none";
    document.getElementById("loading-overlay").classList.remove("hidden");
    boot();
  } catch (err) {
    console.error("handleUsernameConfirm error:", err);
    errorEl.textContent = "เกิดข้อผิดพลาด กรุณาลองใหม่";
    errorEl.style.display = "block";
    btn.disabled = false;
    btn.textContent = "เริ่มการเดินทาง";
  }
}

/* ══════════════════════════════════════════
   BOOT SEQUENCE
══════════════════════════════════════════ */
async function boot() {
  // Guard: ถ้าไม่มี token หยุดทันที
  if (!_accessToken) {
    console.warn("boot() called without token — aborting");
    return;
  }

  initLive2D();

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

  // sync llm_provider จาก server → update UI badge + popup
  if (startData.llm_provider) setLlmProvider(startData.llm_provider);

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

  // แสดง AP/TP tutorial ครั้งแรก
  if (!sessionStorage.getItem("apt_seen")) {
    document.getElementById("ap-tp-tutorial").classList.remove("hidden");
    document.getElementById("ap-tp-dismiss").addEventListener("click", () => {
      document.getElementById("ap-tp-tutorial").classList.add("hidden");
      sessionStorage.setItem("apt_seen", "1");
    });
  }

  if (startData.context)
    await addSystemMessage(startData.context, "#64748b", true);
  if (startData.narrative)
    await addSystemMessage(startData.narrative, "#94a3b8", true);
  if (startData.hint) showHintChips(startData.hint);

  if (startData.is_resuming && startData.raw_turns?.length > 0) {
    // กลับมากลางคัน — restore บทสนทนาที่ค้างไว้
    addSystemMessage("✦ สนทนาต่อจากเดิม ✦", "rgba(255,255,255,0.18)");
    for (const turn of startData.raw_turns) {
      await addMessage("player", turn.player);
      await addMessage("fern", turn.fern, turn.mood || "neutral");
    }
  } else if (startData.intro_text) {
    await addMessage("fern", startData.intro_text, "neutral", true);
  }
}

/* ══════════════════════════════════════════
   HINT CHIPS SYSTEM
══════════════════════════════════════════ */
function showHintChips(hintText) {
  const container = document.getElementById("hint-chips");
  const row = document.getElementById("hint-chips-row");
  if (!container || !row) return;

  // parse hint: "หยิบคทาให้เธอ หรือ ถามว่าเกิดอะไรขึ้น"
  // split on " หรือ " or " / "
  const parts = hintText
    .split(/\s+หรือ\s+|\s*\/\s*/)
    .map((s) => s.trim())
    .filter(Boolean);

  if (parts.length === 0) {
    // ถ้า parse ไม่ออก แสดง hint เดิมเป็น chip เดียว
    parts.push(hintText.replace(/^💡\s*/, "").trim());
  }

  row.innerHTML = "";
  parts.forEach((part) => {
    const chip = document.createElement("button");
    chip.className = "hint-chip";
    chip.textContent = part;
    chip.addEventListener("click", () => {
      DOM.input.value = part;
      DOM.input.dispatchEvent(new Event("input"));
      DOM.input.focus();
      // hide chips after selection
      container.classList.add("hidden");
    });
    row.appendChild(chip);
  });

  container.classList.remove("hidden");
}

// hide hint chips when user starts typing manually
DOM.input.addEventListener("input", () => {
  DOM.input.style.height = "auto";
  DOM.input.style.height = Math.min(DOM.input.scrollHeight, 96) + "px";
  if (DOM.input.value.trim().length > 0) {
    const container = document.getElementById("hint-chips");
    if (container) container.classList.add("hidden");
  }
});

/* ── Signup hint link ── */
const signupLink = document.getElementById("signup-hint-link");
if (signupLink) {
  signupLink.addEventListener("click", (e) => {
    e.preventDefault();
    // เปลี่ยน title และ subtitle ให้รู้สึกเหมือน register flow
    const titleEl = document.querySelector(".ls-title");
    const subtitleEl = document.querySelector(".ls-subtitle");
    if (titleEl) titleEl.textContent = "สร้างบัญชีใหม่";
    if (subtitleEl) subtitleEl.textContent = "เลือกวิธีสมัครสมาชิก";
    signupLink.closest(".ls-signup-link").textContent = "มีบัญชีอยู่แล้ว? ";
    const loginLink = document.createElement("a");
    loginLink.href = "#";
    loginLink.textContent = "เข้าสู่ระบบ";
    loginLink.style.cssText =
      "color:#2563eb;font-weight:600;text-decoration:none";
    loginLink.addEventListener("click", (ev) => {
      ev.preventDefault();
      location.reload();
    });
    signupLink.closest(".ls-signup-link").appendChild(loginLink);
  });
}

/* ══════════════════════════════════════════
   KICK OFF
══════════════════════════════════════════ */
window.addEventListener("DOMContentLoaded", initAuth);
// boot() จะถูกเรียกจาก initAuth เมื่อ login สำเร็จ
