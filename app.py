from dotenv import load_dotenv
load_dotenv()

from game.character import call_fern, summarize_ep, generate_gift_image
import base64
from flask import Flask, request, jsonify, send_from_directory
from game.state import GameState
from game.auth import (
    require_auth,
    load_game_state, save_game_state,
    get_username, save_username,
    get_llm_setting, save_llm_setting,
    get_turns, get_summaries,
)
import os

# BG server URL — ชี้ไปที่ ngrok URL ของ bg_server.py ที่รันบนเครื่องตัวเอง
# ตั้งค่าผ่าน environment variable BG_SERVER_URL ใน Railway
# เช่น BG_SERVER_URL=https://xxxx.ngrok-free.app
BG_SERVER_URL = os.environ.get("BG_SERVER_URL", "http://localhost:5001")

app = Flask(__name__, static_folder="static")

sessions: dict[str, GameState] = {}


def get_or_create_state(user_id: str) -> GameState:
    if user_id not in sessions:
        gs          = GameState()
        gs.user_id  = user_id

        # โหลด summaries ทุก EP ที่ผ่านมา → inject memory
        gs.summaries = get_summaries(user_id)

        # โหลด LLM preference จาก DB
        gs.llm_provider = get_llm_setting(user_id)

        # โหลด game state จาก DB
        saved = load_game_state(user_id)
        if saved and not saved["game_over"]:
            gs.ap            = saved["ap"]
            gs.tp            = saved["tp"]
            gs.current_ep_id = saved["episode"]
            gs.mood_counter  = saved["mood_counter"]
            gs.turn          = saved["turn"]
            gs.route         = saved["route"]

        sessions[user_id] = gs
    return sessions[user_id]


# ══════════════════════════════════════════
#  PROFILE — username
# ══════════════════════════════════════════

@app.route("/api/profile", methods=["GET"])
@require_auth
def api_get_profile():
    username = get_username(request.user_id)
    return jsonify({"username": username})


@app.route("/api/profile", methods=["POST"])
@require_auth
def api_set_profile():
    username = (request.json or {}).get("username", "").strip()
    if not username:
        return jsonify({"error": "username required"}), 400
    if len(username) > 20:
        return jsonify({"error": "username ยาวเกิน 20 ตัวอักษร"}), 400

    ok = save_username(request.user_id, username)
    if not ok:
        return jsonify({"error": "username นี้ถูกใช้แล้ว"}), 409
    return jsonify({"username": username})


# ══════════════════════════════════════════
#  SETTINGS — LLM provider
# ══════════════════════════════════════════

@app.route("/api/settings", methods=["GET"])
@require_auth
def api_get_settings():
    """คืน settings ปัจจุบันของ user"""
    provider = get_llm_setting(request.user_id)
    return jsonify({"llm_provider": provider})


@app.route("/api/settings", methods=["POST"])
@require_auth
def api_set_settings():
    """อัปเดต settings — รองรับ llm_provider: 'gemini' | 'typhoon'"""
    body     = request.json or {}
    provider = body.get("llm_provider", "").strip().lower()

    if provider not in ("gemini", "typhoon"):
        return jsonify({"error": "llm_provider ต้องเป็น 'gemini' หรือ 'typhoon'"}), 400

    ok = save_llm_setting(request.user_id, provider)
    if not ok:
        return jsonify({"error": "บันทึก settings ไม่สำเร็จ"}), 500

    # อัปเดต session ที่กำลังใช้งานอยู่ทันที (ถ้ามี)
    user_id = request.user_id
    if user_id in sessions:
        sessions[user_id].llm_provider = provider

    return jsonify({"llm_provider": provider})


# ══════════════════════════════════════════
#  GAME
# ══════════════════════════════════════════

@app.route("/api/start", methods=["POST"])
@require_auth
def api_start():
    user_id = request.user_id
    force   = (request.json or {}).get("force_new", False)

    # Safety net: ถ้า DB บอก game_over=True แต่ force=False → reset อัตโนมัติ
    if not force:
        saved = load_game_state(user_id)
        if saved and saved.get("game_over"):
            force = True

    if force:
        if user_id in sessions:
            del sessions[user_id]
        from game.auth import supabase
        supabase.table("game_states").delete().eq("user_id", user_id).execute()
        supabase.table("chat_history").delete().eq("user_id", user_id).execute()

    gs = get_or_create_state(user_id)
    ep = gs.current_ep()

    # ── กลับมากลางคัน: ดึง raw turns แทน intro ──
    is_resuming = gs.turn > 0
    raw_turns   = get_turns(user_id, gs.current_ep_id) if is_resuming else []

    return jsonify({
        "ap"           : gs.ap,
        "tp"           : gs.tp,
        "episode"      : gs.current_ep_id,
        "episode_label": gs.episode_label(),
        "bg_prompt"    : ep.get("bg_prompt", ""),
        "context"      : ep.get("context", ""),
        "narrative"    : ep.get("narrative", ""),
        "hint"         : ep.get("hint", ""),
        "intro_text"   : ep.get("fern_intro", "") if not is_resuming else "",
        "raw_turns"    : raw_turns,
        "is_resuming"  : is_resuming,
        "llm_provider" : gs.llm_provider,
    })


@app.route("/api/talk", methods=["POST"])
@require_auth
def api_talk():
    user_id  = request.user_id
    text     = (request.json or {}).get("text", "").strip()
    username = (request.json or {}).get("username", "ผู้เล่น")
    if not text:
        return jsonify({"error": "empty input"}), 400

    gs = get_or_create_state(user_id)

    # sync llm_provider จาก DB ทุก request — ป้องกัน multi-process/worker ไม่ sync
    gs.llm_provider = get_llm_setting(user_id)

    result = gs.process_turn(text)

    save_game_state(user_id, gs)

    result["username"] = username
    return jsonify(result)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/gift", methods=["POST"])
@require_auth
def api_gift():
    body    = request.json or {}
    obj     = body.get("object", "").strip()
    mood    = body.get("mood", "neutral")
    setting = body.get("setting", "")

    if not obj:
        return jsonify({"error": "object required"}), 400
    if len(obj) > 50:
        return jsonify({"error": "ไม่สามารถให้ของขวัญชนิดนี้ได้"}), 400

    img_bytes = generate_gift_image(obj, mood, setting)
    if img_bytes is None:
        return jsonify({"error": "ไม่สามารถสร้างภาพได้"}), 500

    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    return jsonify({"image": f"data:image/png;base64,{img_b64}"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)