# game/auth.py — JWT verification + Supabase client
import os, json
from dotenv import load_dotenv
load_dotenv()
from functools import wraps
from flask import request, jsonify
from supabase import create_client, Client

SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Service client (ใช้ใน Flask server เท่านั้น)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

DEFAULT_LLM = "gemini"
VALID_LLMS  = {"gemini", "typhoon"}


# ══════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════

def get_current_user(token: str) -> dict | None:
    try:
        res = supabase.auth.get_user(token)
        if res and res.user:
            return {"sub": res.user.id}
        return None
    except Exception as e:
        print(f"Auth Error: {e}")
        return None


def require_auth(f):
    """Decorator: ปิดกั้น route ที่ต้อง login"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "unauthorized"}), 401
        token = auth_header[7:]
        user  = get_current_user(token)
        if not user:
            return jsonify({"error": "invalid token"}), 401
        request.user_id = user["sub"]
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════
#  PROFILES (username + llm_provider)
# ══════════════════════════════════════════

def get_username(user_id: str) -> str | None:
    """คืน username หรือ None ถ้ายังไม่ตั้ง"""
    try:
        res = supabase.table("profiles") \
            .select("username") \
            .eq("user_id", user_id) \
            .maybe_single() \
            .execute()
        return res.data["username"] if res.data else None
    except Exception as e:
        print(f"get_username error: {e}")
        return None


def save_username(user_id: str, username: str) -> bool:
    """บันทึก username ครั้งแรก — คืน True ถ้าสำเร็จ"""
    try:
        supabase.table("profiles").upsert(
            {"user_id": user_id, "username": username},
            on_conflict="user_id"
        ).execute()
        return True
    except Exception as e:
        print(f"save_username error: {e}")
        return False


def get_llm_setting(user_id: str) -> str:
    """คืน llm_provider ของ user ('gemini' | 'typhoon') — default: 'gemini'"""
    try:
        res = supabase.table("profiles") \
            .select("llm_provider") \
            .eq("user_id", user_id) \
            .maybe_single() \
            .execute()
        if res.data and res.data.get("llm_provider") in VALID_LLMS:
            return res.data["llm_provider"]
        return DEFAULT_LLM
    except Exception as e:
        print(f"get_llm_setting error: {e}")
        return DEFAULT_LLM


def save_llm_setting(user_id: str, provider: str) -> bool:
    """บันทึก llm_provider — UPDATE เท่านั้น (ป้องกัน not-null constraint บน username)"""
    if provider not in VALID_LLMS:
        return False
    try:
        supabase.table("profiles")             .update({"llm_provider": provider})             .eq("user_id", user_id)             .execute()
        return True
    except Exception as e:
        print(f"save_llm_setting error: {e}")
        return False


# ══════════════════════════════════════════
#  GAME STATE
# ══════════════════════════════════════════

def load_game_state(user_id: str) -> dict | None:
    try:
        res = supabase.table("game_states") \
            .select("*") \
            .eq("user_id", user_id) \
            .maybe_single() \
            .execute()
        return res.data if res else None
    except Exception as e:
        print(f"Load state error: {e}")
        return None


def save_game_state(user_id: str, state_obj) -> None:
    data = {
        "user_id":      user_id,
        "ap":           state_obj.ap,
        "tp":           state_obj.tp,
        "episode":      state_obj.current_ep_id,
        "mood_counter": state_obj.mood_counter,
        "turn":         state_obj.turn,
        "route":        state_obj.route,
        "game_over":    state_obj.game_over,
        "updated_at":   "now()",
    }
    supabase.table("game_states").upsert(data, on_conflict="user_id").execute()


# ══════════════════════════════════════════
#  CHAT HISTORY — raw turns
# ══════════════════════════════════════════

def save_turn(user_id: str, episode: str,
              player: str, fern: str, mood: str) -> None:
    """บันทึก 1 turn ลง chat_history"""
    try:
        supabase.table("chat_history").insert({
            "user_id": user_id,
            "episode": episode,
            "type":    "turn",
            "content": {"player": player, "fern": fern, "mood": mood},
        }).execute()
    except Exception as e:
        print(f"save_turn error: {e}")


def get_turns(user_id: str, episode: str) -> list[dict]:
    """ดึง raw turns ของ EP ปัจจุบัน เรียงตาม created_at"""
    try:
        res = supabase.table("chat_history") \
            .select("content") \
            .eq("user_id", user_id) \
            .eq("episode", episode) \
            .eq("type", "turn") \
            .order("created_at") \
            .execute()
        return [row["content"] for row in (res.data or [])]
    except Exception as e:
        print(f"get_turns error: {e}")
        return []


def delete_turns(user_id: str, episode: str) -> None:
    """ลบ raw turns ของ EP ที่จบแล้ว (summary บันทึกแทนแล้ว)"""
    try:
        supabase.table("chat_history") \
            .delete() \
            .eq("user_id", user_id) \
            .eq("episode", episode) \
            .eq("type", "turn") \
            .execute()
    except Exception as e:
        print(f"delete_turns error: {e}")


# ══════════════════════════════════════════
#  CHAT HISTORY — EP summaries
# ══════════════════════════════════════════

def save_summary(user_id: str, episode: str,
                 summary: str, key_moments: list, fern_feeling: str) -> None:
    """บันทึก summary ของ EP ที่จบแล้ว"""
    try:
        supabase.table("chat_history").insert({
            "user_id": user_id,
            "episode": episode,
            "type":    "summary",
            "content": {
                "summary":      summary,
                "key_moments":  key_moments,
                "fern_feeling": fern_feeling,
            },
        }).execute()
    except Exception as e:
        print(f"save_summary error: {e}")


def get_summaries(user_id: str) -> list[dict]:
    """ดึง summary ทุก EP ที่ผ่านมา เรียงตาม EP"""
    try:
        res = supabase.table("chat_history") \
            .select("episode, content") \
            .eq("user_id", user_id) \
            .eq("type", "summary") \
            .order("created_at") \
            .execute()
        return [
            {"episode": row["episode"], **row["content"]}
            for row in (res.data or [])
        ]
    except Exception as e:
        print(f"get_summaries error: {e}")
        return []